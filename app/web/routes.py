from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..detector import Detector
from ..tracking import IoUTracker

router = APIRouter()
UPLOADS = Path(tempfile.gettempdir()) / "surveillance-mvp-uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)


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
    return {"session_id": session_id, "filename": file.filename, "stream_url": f"/api/stream/{session_id}"}


def _annotated_frames(path: Path):
    capture = cv2.VideoCapture(str(path))
    detector = Detector()
    tracker = IoUTracker()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            for detection in tracker.update(detector.detect(frame)):
                x1, y1, x2, y2 = map(int, detection.bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{detection.object_class} #{detection.track_id} {detection.confidence:.2f}"
                cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
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
    return StreamingResponse(_annotated_frames(matches[0]), media_type="multipart/x-mixed-replace; boundary=frame")
