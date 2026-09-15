"""Capture -> detection -> tracking -> annotation processing pipeline."""

from __future__ import annotations

import threading
import time

import cv2

from .capture import CaptureWorker
from .detector import Detector


class ProcessingPipeline:
    def __init__(self, capture: CaptureWorker, detector: Detector, target_fps: float = 8):
        self.capture, self.detector, self.interval = capture, detector, 1 / target_fps
        self._annotated = None; self._lock = threading.Lock(); self._stop = threading.Event(); self._thread = None
        self.inference_fps = 0.0; self.last_error = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"inference-{self.capture.camera_id}", daemon=True); self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(timeout=2)
    def latest_annotated(self):
        with self._lock: return None if self._annotated is None else self._annotated.copy()
    def _run(self):
        count, started = 0, time.monotonic()
        while not self._stop.is_set():
            frame = self.capture.latest()
            if frame is None: self._stop.wait(self.interval); continue
            try:
                detections = self.detector.track(frame); annotated = frame.copy()
                for detection in detections:
                    x1, y1, x2, y2 = map(int, detection.bbox); color = (0, 255, 0)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    label = f"{detection.object_class} #{detection.track_id} {detection.confidence:.2f}"
                    cv2.putText(annotated, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                with self._lock: self._annotated = annotated
                self.last_error = None; count += 1; elapsed = time.monotonic() - started; self.inference_fps = count / elapsed if elapsed else 0
            except Exception as error:
                self.last_error = str(error)
            self._stop.wait(self.interval)
