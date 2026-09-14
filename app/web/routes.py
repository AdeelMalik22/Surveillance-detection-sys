from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..detector import Detector
from ..events import EventStore
from ..tracking import IoUTracker

router = APIRouter()
UPLOADS = Path(tempfile.gettempdir()) / "surveillance-mvp-uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
EVENTS = EventStore("events.db")
SESSION_EVENTS: dict[str, list[dict]] = {}


@router.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@router.post("/api/uploads")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise HTTPException(400, "upload a supported video file")
    session_id = uuid.uuid4().hex
    destination = UPLOADS / f"{session_id}{suffix}"
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    SESSION_EVENTS[session_id] = []
    return {"session_id": session_id, "filename": file.filename, "stream_url": f"/api/stream/{session_id}"}


def _annotated_frames(session_id: str, path: Path, start_seconds: float = 0):
    capture = cv2.VideoCapture(str(path))
    if start_seconds > 0:
        capture.set(cv2.CAP_PROP_POS_MSEC, start_seconds * 1000)
    # The browser stream prioritizes responsiveness on CPU. The standalone
    # detection script can use a larger image size for maximum recall.
    detector = Detector(confidence=0.3, image_size=416)
    tracker = IoUTracker()
    frame_number = 0
    tracked_detections = []
    seen_tracks: set[int] = set()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_number % 8 == 0:
                tracked_detections = tracker.update(detector.detect(frame))
            else:
                # Drop intermediate source frames instead of queuing stale
                # images behind a slower CPU inference pass.
                frame_number += 1
                continue
            frame_number += 1
            for detection in tracked_detections:
                if detection.track_id not in seen_tracks:
                    seen_tracks.add(detection.track_id)
                    event = EVENTS.add(session_id, "camera-view", detection.object_class, detection.confidence, detection.bbox)
                    SESSION_EVENTS.setdefault(session_id, []).append(event)
                x1, y1, x2, y2 = map(int, detection.bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{detection.object_class} #{detection.track_id} {detection.confidence:.2f}"
                cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
    finally:
        capture.release()


@router.get("/api/stream/{session_id}")
def stream(session_id: str, start: float = 0):
    matches = list(UPLOADS.glob(f"{session_id}.*"))
    if not matches:
        raise HTTPException(404, "upload session not found")
    return StreamingResponse(_annotated_frames(session_id, matches[0], max(0, start)), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/events/{session_id}")
def session_events(session_id: str):
    if session_id not in SESSION_EVENTS:
        raise HTTPException(404, "upload session not found")
    return {"count": len(SESSION_EVENTS[session_id]), "events": SESSION_EVENTS[session_id]}
