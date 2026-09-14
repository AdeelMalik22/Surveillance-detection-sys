from __future__ import annotations

import shutil
import threading
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
CLIPS = UPLOADS / "clips"
CLIPS.mkdir(parents=True, exist_ok=True)
EVENTS = EventStore("events.db")
SESSION_EVENTS: dict[str, list[dict]] = {}


def _save_clip(source: Path, session_id: str, event_id: int, at_seconds: float, before: float = 3, after: float = 5) -> str | None:
    reader = cv2.VideoCapture(str(source))
    fps = reader.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(reader.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        reader.release(); return None
    start = max(0.0, at_seconds - before); end = at_seconds + after
    reader.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    output_path = CLIPS / f"{session_id}-{event_id}.mp4"
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    try:
        while reader.isOpened():
            current = reader.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if current > end: break
            ok, frame = reader.read()
            if not ok: break
            writer.write(frame)
    finally:
        reader.release(); writer.release()
    return output_path.name if output_path.exists() and output_path.stat().st_size else None


def _create_event_clip(session_id: str, source: Path, event: dict, at_seconds: float) -> None:
    clip_name = _save_clip(source, session_id, event["id"], at_seconds)
    event["clip_available"] = clip_name is not None


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
                    event["clip_url"] = f"/api/events/{session_id}/{event['id']}/clip"
                    event["clip_available"] = False
                    SESSION_EVENTS.setdefault(session_id, []).append(event)
                    threading.Thread(target=_create_event_clip, args=(session_id, path, event, capture.get(cv2.CAP_PROP_POS_MSEC) / 1000), daemon=True).start()
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


@router.get("/api/events/{session_id}/{event_id}/clip")
def event_clip(session_id: str, event_id: int):
    clip = CLIPS / f"{session_id}-{event_id}.mp4"
    if not clip.exists():
        raise HTTPException(404, "event clip is not available")
    return FileResponse(clip, media_type="video/mp4", filename=clip.name)
