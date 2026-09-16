"""Shared continuous zone-incident lifecycle.

The manager is deliberately independent of OpenCV and SQLite details. A
caller supplies callbacks for opening, updating, closing, and recording an
incident's frames.
"""

from __future__ import annotations

from collections.abc import Callable


EMPTY_OCCUPANCY = {"detections": [], "classes": set(), "track_ids": set()}


class IncidentManager:
    def __init__(
        self,
        clear_frames: int,
        on_open: Callable[[str, dict, int], object],
        on_update: Callable[[object, dict, int], None],
        on_close: Callable[[object, int], None],
        on_frame: Callable[[object, object], None] | None = None,
    ):
        if clear_frames < 1:
            raise ValueError("clear_frames must be positive")
        self.clear_frames = clear_frames
        self.on_open = on_open
        self.on_update = on_update
        self.on_close = on_close
        self.on_frame = on_frame
        self.active: dict[str, object] = {}

    def process(self, occupancy: dict, frame: object, frame_number: int) -> None:
        """Advance all incidents for one processed frame."""
        for zone_id, incident in list(self.active.items()):
            if self.on_frame is not None:
                self.on_frame(incident, frame)
            current = occupancy.get(zone_id, EMPTY_OCCUPANCY)
            if current["detections"]:
                self.on_update(incident, current, frame_number)
            elif frame_number - incident["last_occupied_frame"] >= self.clear_frames:
                self.on_close(incident, frame_number)
                del self.active[zone_id]

        for zone_id, current in occupancy.items():
            if current["detections"] and zone_id not in self.active:
                self.active[zone_id] = self.on_open(zone_id, current, frame_number)

    def close_all(self, frame_number: int) -> None:
        for incident in list(self.active.values()):
            self.on_close(incident, frame_number)
        self.active.clear()
