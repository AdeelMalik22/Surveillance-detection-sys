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
from ..zones import ZoneEngine

router = APIRouter()
UPLOADS = Path(tempfile.gettempdir()) / "surveillance-mvp-uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
SESSION_COUNTS: dict[str, dict[str, int]] = {}
SESSION_ZONES: dict[str, dict[str, list[list[float]]]] = {}
DEMO_EVENTS = EventStore()
ZONE_COLOR = (116, 223, 187)


@router.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@router.get("/ui/static/{asset_path:path}", include_in_schema=False)
def ui_asset(asset_path: str):
    root = (Path(__file__).parent / "static").resolve()
    file = (root / asset_path).resolve()
    if root not in file.parents or not file.is_file():
        raise HTTPException(404, "UI asset not found")
    return FileResponse(file)


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
    SESSION_ZONES[session_id] = {}
    return {"session_id": session_id, "filename": file.filename, "stream_url": f"/api/stream/{session_id}"}


def register_session_zone(session_id: str, zone_id: str, polygon: list[list[float]]) -> None:
    if session_id in SESSION_COUNTS:
        SESSION_ZONES.setdefault(session_id, {})[zone_id] = polygon


def unregister_session_zone(session_id: str, zone_id: str) -> None:
    if session_id in SESSION_ZONES:
        SESSION_ZONES[session_id].pop(zone_id, None)


def _draw_zones(frame, session_id: str) -> None:
    for zone_id, polygon in SESSION_ZONES.get(session_id, {}).items():
        if len(polygon) < 3:
            continue
        points = [(int(x), int(y)) for x, y in polygon]
        for start, end in zip(points, points[1:] + points[:1]):
            cv2.line(frame, start, end, ZONE_COLOR, 2)
        x, y = points[0]
        cv2.putText(frame, zone_id, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, ZONE_COLOR, 2)


def _annotated_frames(session_id: str, path: Path):
    capture = cv2.VideoCapture(str(path))
    detector = Detector(model_path="yolov8s.pt", confidence=0.3, image_size=960, tracker=str(Path(__file__).parents[1] / "bytetrack.yaml"))
    frame_number = 0
    tracked_detections = []
    zone_signature = None
    zone_engine = ZoneEngine({})
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_number % 3 == 0:
                tracked_detections = detector.track(frame)
            frame_number += 1
            current_zones = SESSION_ZONES.get(session_id, {})
            current_signature = tuple((zone_id, tuple(tuple(point) for point in polygon)) for zone_id, polygon in sorted(current_zones.items()))
            if current_signature != zone_signature:
                zone_engine = ZoneEngine(current_zones)
                zone_signature = current_signature
            counts = {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
            for detection in tracked_detections:
                if detection.object_class in counts:
                    counts[detection.object_class] += 1
                track_id = detection.track_id if detection.track_id is not None else "?"
                x1, y1, x2, y2 = map(int, detection.bbox)
                color = (0, 0, 255) if detection.object_class in {"car", "truck"} else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"{detection.object_class} #{track_id} {detection.confidence:.2f}"
                cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            for detection, zone_id in zone_engine.entries([d for d in tracked_detections if d.track_id is not None]):
                DEMO_EVENTS.add(session_id, zone_id, detection.object_class, detection.confidence, detection.bbox)
            _draw_zones(frame, session_id)
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
    return SESSION_COUNTS[session_id]
