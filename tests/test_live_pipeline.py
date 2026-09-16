import numpy as np

from app.infrastructure.events import EventStore
from app.processing.detector import DetectionResult
from app.processing.incidents import IncidentManager
from app.processing.pipeline import ProcessingPipeline
from app.processing.zones import occupancy


class FakeCapture:
    camera_id = "camera-1"


class FakeDetector:
    def __init__(self):
        self.detections = []

    def track(self, _frame):
        return self.detections


def test_live_pipeline_creates_and_closes_zone_event(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    detector = FakeDetector()
    zones = {"entrance": [[0, 0], [100, 0], [100, 100], [0, 100]]}
    active = {}

    def open_incident(zone_id, current, frame_number):
        detection = current["detections"][0]
        event = store.add("camera-1", zone_id, detection.object_class, detection.confidence, detection.bbox,
                          {"status": "open", "start_frame": frame_number})
        incident = {"event_id": event["id"], "last_occupied_frame": frame_number,
                    "start_frame": frame_number}
        active[zone_id] = incident
        return incident

    def update_incident(incident, current, frame_number):
        incident["last_occupied_frame"] = frame_number

    def close_incident(incident, frame_number):
        store.update_metadata(incident["event_id"], status="closed", end_frame=frame_number)

    manager = IncidentManager(2, open_incident, update_incident, close_incident)

    def on_detections(detections, _frame, frame_number):
        manager.process(occupancy(zones, detections), _frame, frame_number)

    pipeline = ProcessingPipeline(FakeCapture(), detector, target_fps=8, on_detections=on_detections)
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    detector.detections = [DetectionResult("person", 0, 0.9, [20, 20, 40, 80], 1)]
    pipeline.process_frame(frame, 1)
    assert store.list()[0]["status"] == "open"

    pipeline.process_frame(frame, 2)
    detector.detections = []
    pipeline.process_frame(frame, 3)
    pipeline.process_frame(frame, 4)

    event = store.list()[0]
    assert event["status"] == "closed"
    assert event["end_frame"] == 4
    assert pipeline.latest_annotated() is not None
