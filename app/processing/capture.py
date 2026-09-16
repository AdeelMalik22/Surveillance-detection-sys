from __future__ import annotations
import threading, time
from dataclasses import dataclass
import cv2

@dataclass
class CameraStatus:
    camera_id: str
    connected: bool = False
    capture_fps: float = 0.0
    last_frame_at: float | None = None
    last_error: str | None = None

class CaptureWorker:
    def __init__(self, camera_id, source, target_fps=8):
        self.camera_id, self.source, self.interval = camera_id, source, 1 / target_fps
        self.status = CameraStatus(camera_id); self._frame = None; self._lock = threading.Lock(); self._stop = threading.Event(); self._thread = None
    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"capture-{self.camera_id}", daemon=True); self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(timeout=2)
    def latest(self):
        with self._lock: return None if self._frame is None else self._frame.copy()
    def _run(self):
        while not self._stop.is_set():
            capture = cv2.VideoCapture(self.source)
            if not capture.isOpened():
                self.status.connected = False; self.status.last_error = "unable to open source"; capture.release(); self._stop.wait(2); continue
            self.status.connected, self.status.last_error = True, None; count, started = 0, time.monotonic()
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok: self.status.connected = False; self.status.last_error = "frame read failed; reconnecting"; break
                if frame.shape[1] > 640:
                    height = int(frame.shape[0] * 640 / frame.shape[1]); frame = cv2.resize(frame, (640, height))
                with self._lock: self._frame = frame
                count += 1; self.status.last_frame_at = time.time(); elapsed = time.monotonic() - started; self.status.capture_fps = count / elapsed if elapsed else 0; self._stop.wait(self.interval)
            capture.release(); self._stop.wait(1)
