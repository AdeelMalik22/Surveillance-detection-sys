"""Business operations for surveillance events and event media."""

import json
import shutil

from . import surveillance


def list_events(store, limit=50, offset=0, **filters):
    return store.list(limit, offset, **filters)


def clear_events(store):
    row = store.db.execute("SELECT COUNT(*) AS count FROM events").fetchone()
    deleted = int(row["count"])
    store.db.execute("DELETE FROM events")
    store.db.commit()
    for path in surveillance.CLIPS.glob("event-*"):
        if path.is_dir():
            shutil.rmtree(path)
    return deleted


def clip_fps(store, event_id: int) -> float:
    row = store.db.execute(
        "SELECT metadata FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if not row:
        return float(surveillance.CLIP_FPS)
    metadata = json.loads(row["metadata"] or "{}")
    return float(metadata.get("clip_fps", surveillance.CLIP_FPS))
