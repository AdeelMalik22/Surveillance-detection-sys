"""YOLO object detection for the supported surveillance classes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_CLASSES = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass(frozen=True)
class DetectionResult:
    """One model detection in xyxy pixel coordinates."""

    object_class: str
    class_id: int
    confidence: float
    bbox: list[float]


class Detector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.5, device: str = "auto"):
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics is required for detection; install it with `pip install ultralytics`") from exc

        self.model_path = model_path
        self.confidence = confidence
        self.device = None if device == "auto" else device
        self.model = YOLO(model_path)

    def detect(self, frame: Any) -> list[DetectionResult]:
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            classes=list(SUPPORTED_CLASSES),
            device=self.device,
            verbose=False,
        )
        if not results:
            return []

        boxes = results[0].boxes
        detections: list[DetectionResult] = []
        for box, class_id, confidence in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist()):
            class_id = int(class_id)
            if class_id not in SUPPORTED_CLASSES:
                continue
            detections.append(DetectionResult(SUPPORTED_CLASSES[class_id], class_id, float(confidence), [float(value) for value in box]))
        return detections
