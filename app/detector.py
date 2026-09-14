"""YOLO object detection for the supported surveillance classes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import sys

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
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.3, device: str = "auto", image_size: int = 960):
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if image_size < 320:
            raise ValueError("image_size must be at least 320")
        try:
            # Some Python 3.11 release-candidate builds lack APIs expected by
            # current PyTorch. Stable Python 3.11 remains the recommended fix.
            if not hasattr(sys, "get_int_max_str_digits"):
                def get_int_max_str_digits() -> int:
                    return 4300
                sys.get_int_max_str_digits = get_int_max_str_digits
            if not hasattr(sys, "set_int_max_str_digits"):
                def set_int_max_str_digits(maxdigits: int) -> None:
                    return None
                sys.set_int_max_str_digits = set_int_max_str_digits
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics is required for detection; install it with `pip install ultralytics`") from exc

        self.model_path = model_path
        self.confidence = confidence
        self.image_size = image_size
        self.device = None if device == "auto" else device
        self.model = YOLO(model_path)

    def detect(self, frame: Any) -> list[DetectionResult]:
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            imgsz=self.image_size,
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
