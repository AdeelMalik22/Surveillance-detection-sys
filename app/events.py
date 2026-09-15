import json, sqlite3
from datetime import datetime, timezone

class EventStore:
    def __init__(self, path="events.db"):
        self.db = sqlite3.connect(path, check_same_thread=False); self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, camera_id TEXT, zone_id TEXT, object_class TEXT, confidence REAL, timestamp TEXT, bbox TEXT, metadata TEXT DEFAULT '{}')")
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(events)").fetchall()}
        if "metadata" not in columns:
            self.db.execute("ALTER TABLE events ADD COLUMN metadata TEXT DEFAULT '{}'")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_camera_zone ON events(camera_id, zone_id)")
        self.db.commit()
    def add(self, camera_id, zone_id, object_class, confidence, bbox, metadata=None):
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc).isoformat(); cur = self.db.execute("INSERT INTO events(camera_id,zone_id,object_class,confidence,timestamp,bbox,metadata) VALUES(?,?,?,?,?,?,?)", (camera_id, zone_id, object_class, confidence, timestamp, json.dumps(bbox), json.dumps(metadata))); self.db.commit()
        return {"id": cur.lastrowid, "camera_id": camera_id, "zone_id": zone_id, "object_class": object_class, "confidence": confidence, "timestamp": timestamp, "bbox": bbox, **metadata}
    def update_metadata(self, event_id, **metadata):
        row = self.db.execute("SELECT metadata FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            return None
        current = json.loads(row["metadata"] or "{}")
        current.update(metadata)
        self.db.execute("UPDATE events SET metadata = ? WHERE id = ?", (json.dumps(current), event_id))
        self.db.commit()
        return current
    def list(self, limit=50, offset=0, **filters):
        clauses, values = [], []
        for key in ("camera_id", "zone_id", "object_class"):
            if filters.get(key): clauses.append(f"{key} = ?"); values.append(filters[key])
        if filters.get("from"): clauses.append("timestamp >= ?"); values.append(filters["from"])
        if filters.get("to"): clauses.append("timestamp <= ?"); values.append(filters["to"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""; rows = self.db.execute(f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*values, limit, offset)).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["bbox"] = json.loads(row["bbox"])
            event.update(json.loads(row["metadata"] or "{}"))
            event.pop("metadata", None)
            events.append(event)
        return events


class CameraStore:
    def __init__(self, connection):
        self.db = connection
        self.db.execute("CREATE TABLE IF NOT EXISTS cameras (id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL, stream_url TEXT NOT NULL, created_at TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS camera_zones (camera_id TEXT NOT NULL, zone_id TEXT NOT NULL, polygon TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(camera_id, zone_id))")
        self.db.commit()

    def add_camera(self, camera_id, filename, path, stream_url):
        created_at = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT OR REPLACE INTO cameras(id,filename,path,stream_url,created_at) VALUES(?,?,?,?,?)", (camera_id, filename, path, stream_url, created_at))
        self.db.commit()
        return {"session_id": camera_id, "filename": filename, "path": path, "stream_url": stream_url, "created_at": created_at}

    def list_cameras(self):
        rows = self.db.execute("SELECT * FROM cameras ORDER BY created_at DESC").fetchall()
        cameras = []
        for row in rows:
            zones = self.list_zones(row["id"])
            cameras.append({"session_id": row["id"], "filename": row["filename"], "stream_url": row["stream_url"], "created_at": row["created_at"], "zones": zones})
        return cameras

    def get_camera(self, camera_id):
        row = self.db.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        if not row:
            return None
        return {"session_id": row["id"], "filename": row["filename"], "path": row["path"], "stream_url": row["stream_url"], "created_at": row["created_at"], "zones": self.list_zones(camera_id)}

    def delete_camera(self, camera_id):
        row = self.db.execute("SELECT path FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        if not row:
            return None
        self.db.execute("DELETE FROM camera_zones WHERE camera_id = ?", (camera_id,))
        self.db.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
        self.db.commit()
        return row["path"]

    def add_zone(self, camera_id, zone_id, polygon):
        created_at = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT OR REPLACE INTO camera_zones(camera_id,zone_id,polygon,created_at) VALUES(?,?,?,?)", (camera_id, zone_id, json.dumps(polygon), created_at))
        self.db.commit()

    def delete_zone(self, camera_id, zone_id):
        self.db.execute("DELETE FROM camera_zones WHERE camera_id = ? AND zone_id = ?", (camera_id, zone_id))
        self.db.commit()

    def list_zones(self, camera_id):
        rows = self.db.execute("SELECT zone_id, polygon, created_at FROM camera_zones WHERE camera_id = ? ORDER BY created_at", (camera_id,)).fetchall()
        return [{"id": row["zone_id"], "polygon": json.loads(row["polygon"]), "created_at": row["created_at"]} for row in rows]
