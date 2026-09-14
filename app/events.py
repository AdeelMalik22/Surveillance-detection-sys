import json, sqlite3
from datetime import datetime, timezone

class EventStore:
    def __init__(self, path="events.db"):
        self.db = sqlite3.connect(path, check_same_thread=False); self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, camera_id TEXT, zone_id TEXT, object_class TEXT, confidence REAL, timestamp TEXT, bbox TEXT)"); self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp)"); self.db.commit()
    def add(self, camera_id, zone_id, object_class, confidence, bbox):
        timestamp = datetime.now(timezone.utc).isoformat(); cur = self.db.execute("INSERT INTO events(camera_id,zone_id,object_class,confidence,timestamp,bbox) VALUES(?,?,?,?,?,?)", (camera_id, zone_id, object_class, confidence, timestamp, json.dumps(bbox))); self.db.commit()
        return {"id": cur.lastrowid, "camera_id": camera_id, "zone_id": zone_id, "object_class": object_class, "confidence": confidence, "timestamp": timestamp, "bbox": bbox}
    def list(self, limit=50, offset=0, **filters):
        clauses, values = [], []
        for key in ("camera_id", "zone_id", "object_class"):
            if filters.get(key): clauses.append(f"{key} = ?"); values.append(filters[key])
        if filters.get("from"): clauses.append("timestamp >= ?"); values.append(filters["from"])
        if filters.get("to"): clauses.append("timestamp <= ?"); values.append(filters["to"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""; rows = self.db.execute(f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*values, limit, offset)).fetchall()
        return [{**dict(row), "bbox": json.loads(row["bbox"])} for row in rows]
