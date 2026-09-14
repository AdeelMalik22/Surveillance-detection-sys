from app.zones import Detection, ZoneEngine

def test_zone_entry_is_emitted_once_until_exit():
    engine = ZoneEngine({"z": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    detection = Detection("person", 0.9, [2, 2, 4, 8], 1)
    assert len(engine.entries([detection])) == 1
    assert len(engine.entries([detection])) == 0
    engine.entries([])
    assert len(engine.entries([detection])) == 1
