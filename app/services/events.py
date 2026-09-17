"""Business operations for surveillance events and event media."""

import json
import shutil
from datetime import datetime

from . import surveillance


def list_events(store, limit=50, offset=0, **filters):
    validate_filters(filters)
    return store.list(limit, offset, **filters)


def validate_filters(filters):
    for name in ("from", "to"):
        value = filters.get(name)
        if value:
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"invalid '{name}' timestamp; use ISO-8601 format") from exc
    if filters.get("from") and filters.get("to"):
        start = datetime.fromisoformat(filters["from"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(filters["to"].replace("Z", "+00:00"))
        if start > end:
            raise ValueError("'from' timestamp must be earlier than or equal to 'to'")
    allowed_classes = {"person", "car", "motorcycle", "bus", "truck", "person + vehicle", "vehicle", "object"}
    if filters.get("object_class") and filters["object_class"] not in allowed_classes:
        raise ValueError("invalid object_class filter")


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
