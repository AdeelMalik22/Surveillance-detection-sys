from app.zones import Detection, ZoneEngine, incident_summary, occupancy

def test_zone_entry_is_emitted_once_until_exit():
    engine = ZoneEngine({"z": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    detection = Detection("person", 0.9, [2, 2, 4, 8], 1)
    assert len(engine.entries([detection])) == 1
    assert len(engine.entries([detection])) == 0
    engine.entries([])
    assert len(engine.entries([detection])) == 1


def test_occupancy_uses_bottom_center_and_collects_incident_metadata():
    detection = Detection("person", 0.9, [2, 2, 4, 8], 7)
    result = occupancy({"z": [[0, 0], [10, 0], [10, 10], [0, 10]]}, [detection])

    assert result["z"]["detections"] == [detection]
    assert result["z"]["classes"] == {"person"}
    assert result["z"]["track_ids"] == {7}
    assert incident_summary({"person", "car"}) == "person + vehicle"
