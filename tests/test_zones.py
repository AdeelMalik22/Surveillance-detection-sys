from app.processing.detector import DetectionResult
from app.processing.zones import incident_summary, occupancy
from app.processing.incidents import IncidentManager

def test_occupancy_uses_bottom_center_and_collects_incident_metadata():
    detection = DetectionResult("person", 0, 0.9, [2, 2, 4, 8], 7)
    result = occupancy({"z": [[0, 0], [10, 0], [10, 10], [0, 10]]}, [detection])

    assert result["z"]["detections"] == [detection]
    assert result["z"]["classes"] == {"person"}
    assert result["z"]["track_ids"] == {7}
    assert incident_summary({"person", "car"}) == "person + vehicle"


def test_incident_manager_opens_updates_and_closes_after_clear_period():
    calls = []

    manager = IncidentManager(
        clear_frames=2,
        on_open=lambda zone, current, number: calls.append(("open", zone, number)) or {"last_occupied_frame": number},
        on_update=lambda incident, current, number: calls.append(("update", number)) or incident.update(last_occupied_frame=number),
        on_close=lambda incident, number: calls.append(("close", number)),
    )
    occupied = {"z": {"detections": [object()], "classes": set(), "track_ids": set()}}
    empty = {"z": {"detections": [], "classes": set(), "track_ids": set()}}

    manager.process(occupied, None, 1)
    manager.process(occupied, None, 2)
    manager.process(empty, None, 3)
    manager.process(empty, None, 4)

    assert calls == [("open", "z", 1), ("update", 2), ("close", 4)]
