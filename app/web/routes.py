from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..detector import Detector

router = APIRouter()
UPLOADS = Path(tempfile.gettempdir()) / "surveillance-mvp-uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
SESSION_COUNTS: dict[str, dict[str, int]] = {}
SESSION_SEEN_TRACKS: dict[str, set[int]] = {}


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
    SESSION_COUNTS[session_id] = {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0}
    SESSION_SEEN_TRACKS[session_id] = set()
    return {"session_id": session_id, "filename": file.filename, "stream_url": f"/api/stream/{session_id}"}


def _annotated_frames(session_id: str, path: Path):
    capture = cv2.VideoCapture(str(path))
    detector = Detector(confidence=0.3, image_size=960)
    frame_number = 0
    tracked_detections = []
    counts = SESSION_COUNTS[session_id].copy()
    seen_tracks = SESSION_SEEN_TRACKS[session_id]
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_number % 3 == 0:
                tracked_detections = detector.track(frame)
            frame_number += 1
            for detection in tracked_detections:
                track_id = detection.track_id if detection.track_id is not None else id(detection)
                if track_id not in seen_tracks:
                    seen_tracks.add(track_id)
                    if detection.object_class in counts:
                        counts[detection.object_class] += 1
                x1, y1, x2, y2 = map(int, detection.bbox)
                color = (0, 0, 255) if detection.object_class in {"car", "truck"} else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"{detection.object_class} #{track_id} {detection.confidence:.2f}"
                cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            counts["total"] = sum(counts[key] for key in ("person", "car", "motorcycle", "bus", "truck"))
            SESSION_COUNTS[session_id] = counts.copy()
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
    finally:
        capture.release()


@router.get("/api/stream/{session_id}")
def stream(session_id: str):
    matches = list(UPLOADS.glob(f"{session_id}.*"))
    if not matches:
        raise HTTPException(404, "upload session not found")
    return StreamingResponse(_annotated_frames(session_id, matches[0]), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/counts/{session_id}")
def counts(session_id: str):
    if session_id not in SESSION_COUNTS:
        raise HTTPException(404, "upload session not found")
    return SESSION_COUNTS[session_id]


@router.post("/api/reset/{session_id}")
def reset_counts(session_id: str):
    if session_id not in SESSION_COUNTS:
        raise HTTPException(404, "upload session not found")
    SESSION_COUNTS[session_id] = {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0}
    SESSION_SEEN_TRACKS[session_id] = set()
    return SESSION_COUNTS[session_id]
