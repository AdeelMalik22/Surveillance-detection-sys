from app.detector import DetectionResult
from app.tracking import IoUTracker


def test_iou_tracker_keeps_identity_between_frames():
    tracker = IoUTracker(iou_threshold=0.2)
    first = tracker.update([DetectionResult("person", 0.9, 0, [0, 0, 10, 10])])
    second = tracker.update([DetectionResult("person", 0.8, 0, [1, 1, 11, 11])])
    assert first[0].track_id == second[0].track_id


def test_tracker_does_not_match_different_classes():
    tracker = IoUTracker(iou_threshold=0.2)
    first = tracker.update([DetectionResult("person", 0.9, 0, [0, 0, 10, 10])])
    second = tracker.update([DetectionResult("car", 0.8, 2, [1, 1, 11, 11])])
    assert first[0].track_id != second[0].track_id
