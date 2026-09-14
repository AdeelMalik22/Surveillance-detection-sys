"""Small CPU-friendly IoU tracker for temporary object identities."""

from __future__ import annotations

from dataclasses import dataclass

from .detector import DetectionResult
from .zones import Detection


def _iou(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0]); y1 = max(left[1], right[1])
    x2 = min(left[2], right[2]); y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


@dataclass
class _Track:
    track_id: int
    object_class: str
    bbox: list[float]
    missed: int = 0


class IoUTracker:
    def __init__(self, iou_threshold: float = 0.3, max_age: int = 10):
        if not 0 <= iou_threshold <= 1: raise ValueError("iou_threshold must be between 0 and 1")
        if max_age < 0: raise ValueError("max_age must be non-negative")
        self.iou_threshold, self.max_age = iou_threshold, max_age
        self._tracks: list[_Track] = []
        self._next_id = 1

    def update(self, detections: list[DetectionResult]) -> list[Detection]:
        assignments: dict[int, int] = {}
        used_tracks: set[int] = set()
        ordered = sorted(((index, detection) for index, detection in enumerate(detections)), key=lambda item: item[1].confidence, reverse=True)
        for detection_index, detection in ordered:
            candidates = [(track_index, _iou(detection.bbox, track.bbox)) for track_index, track in enumerate(self._tracks) if track_index not in used_tracks and track.object_class == detection.object_class]
            if candidates:
                track_index, score = max(candidates, key=lambda item: item[1])
                if score >= self.iou_threshold:
                    assignments[detection_index] = track_index; used_tracks.add(track_index)

        for index, track in enumerate(self._tracks):
            if index not in used_tracks: track.missed += 1
        for detection_index, track_index in assignments.items():
            track = self._tracks[track_index]; detection = detections[detection_index]; track.bbox = detection.bbox; track.missed = 0
        for detection_index, detection in enumerate(detections):
            if detection_index not in assignments:
                self._tracks.append(_Track(self._next_id, detection.object_class, detection.bbox)); assignments[detection_index] = len(self._tracks) - 1; self._next_id += 1
        self._tracks = [track for track in self._tracks if track.missed <= self.max_age]
        return [Detection(d.object_class, d.confidence, d.bbox, self._tracks[index].track_id) for index, d in enumerate(detections) for index in [assignments[index]]]
