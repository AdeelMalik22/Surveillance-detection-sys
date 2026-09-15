from __future__ import annotations

import shutil
import tempfile
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from shapely.geometry import Point, Polygon

from ..detector import Detector
from ..events import CameraStore, EventStore

router = APIRouter()
UPLOADS = Path(tempfile.gettempdir()) / "surveillance-mvp-uploads"
CLIPS = Path(tempfile.gettempdir()) / "surveillance-mvp-event-clips"
UPLOADS.mkdir(parents=True, exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)
SESSION_COUNTS: dict[str, dict[str, int]] = {}
SESSION_ZONES: dict[str, dict[str, list[list[float]]]] = {}
DEMO_EVENTS = EventStore()
CAMERAS = CameraStore(DEMO_EVENTS.db)
ZONE_COLOR = (116, 223, 187)
CLIP_FPS = 8
CLIP_PRE_SECONDS = 2
CLIP_POST_SECONDS = 4
ZONE_CLEAR_SECONDS = 2
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}


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
    return CAMERAS.add_camera(session_id, file.filename, str(destination), f"/api/stream/{session_id}")


@router.get("/api/cameras")
def list_uploaded_cameras():
    cameras = CAMERAS.list_cameras()
    for camera in cameras:
        SESSION_COUNTS.setdefault(camera["session_id"], {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0})
        SESSION_ZONES[camera["session_id"]] = {zone["id"]: zone["polygon"] for zone in camera.get("zones", [])}
    return cameras


@router.delete("/api/cameras/{session_id}", status_code=204)
def delete_uploaded_camera(session_id: str):
    path = CAMERAS.delete_camera(session_id)
    if path is None:
        raise HTTPException(404, "camera not found")
    SESSION_COUNTS.pop(session_id, None)
    SESSION_ZONES.pop(session_id, None)
    file_path = Path(path)
    if file_path.is_file():
        file_path.unlink()


def register_session_zone(session_id: str, zone_id: str, polygon: list[list[float]]) -> None:
    camera = CAMERAS.get_camera(session_id)
    if camera:
        SESSION_COUNTS.setdefault(session_id, {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0})
        SESSION_ZONES.setdefault(session_id, {})[zone_id] = polygon
        CAMERAS.add_zone(session_id, zone_id, polygon)


def unregister_session_zone(session_id: str, zone_id: str) -> None:
    if session_id in SESSION_ZONES:
        SESSION_ZONES[session_id].pop(zone_id, None)
    CAMERAS.delete_zone(session_id, zone_id)


def _draw_zones(frame, session_id: str) -> None:
    for zone_id, polygon in SESSION_ZONES.get(session_id, {}).items():
        if len(polygon) < 3:
            continue
        points = [(int(x), int(y)) for x, y in polygon]
        for start, end in zip(points, points[1:] + points[:1]):
            cv2.line(frame, start, end, ZONE_COLOR, 2)
        x, y = points[0]
        cv2.putText(frame, zone_id, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, ZONE_COLOR, 2)


def _clip_dir(event_id: int) -> Path:
    return CLIPS / f"event-{event_id}"


def _append_clip_frame(clip: dict, frame) -> None:
    frame_path = clip["path"] / f"frame-{clip['index']:04d}.jpg"
    ok, encoded = cv2.imencode(".jpg", frame)
    if ok:
        frame_path.write_bytes(encoded.tobytes())
        clip["index"] += 1


def _object_summary(classes: set[str]) -> str:
    has_person = "person" in classes
    has_vehicle = bool(classes & VEHICLE_CLASSES)
    if has_person and has_vehicle:
        return "person + vehicle"
    if has_vehicle:
        return "vehicle"
    if has_person:
        return "person"
    return "object"


def _zone_occupancy(zones: dict[str, list[list[float]]], detections) -> dict[str, dict]:
    occupancy = {
        zone_id: {"detections": [], "classes": set(), "track_ids": set()}
        for zone_id in zones
    }
    polygons = {zone_id: Polygon(points) for zone_id, points in zones.items() if len(points) >= 3}
    for detection in detections:
        x1, _y1, x2, y2 = detection.bbox
        point = Point((x1 + x2) / 2, y2)
        for zone_id, polygon in polygons.items():
            if polygon.covers(point):
                occupancy[zone_id]["detections"].append(detection)
                occupancy[zone_id]["classes"].add(detection.object_class)
                if detection.track_id is not None:
                    occupancy[zone_id]["track_ids"].add(detection.track_id)
    return occupancy


def _start_zone_incident(session_id: str, zone_id: str, occupancy: dict, buffered_frames, current_frame, path: Path, frame_number: int) -> dict:
    classes = occupancy["classes"]
    detections = occupancy["detections"]
    best_detection = max(detections, key=lambda item: item.confidence)
    event = DEMO_EVENTS.add(
        session_id,
        zone_id,
        _object_summary(classes),
        best_detection.confidence,
        best_detection.bbox,
        {
            "event_type": "zone_occupancy",
            "status": "open",
            "start_frame": frame_number,
            "end_frame": None,
            "duration_seconds": None,
            "source_video": path.name,
            "object_classes": sorted(classes),
            "track_ids": sorted(occupancy["track_ids"]),
            "max_occupancy": len(detections),
            "clip_status": "recording",
            "clip_type": "image_sequence",
            "clip_fps": CLIP_FPS,
            "clip_frame_count": 0,
            "clip_url": f"/api/events/{{event_id}}/clip",
        },
    )
    DEMO_EVENTS.update_metadata(event["id"], clip_url=f"/api/events/{event['id']}/clip")
    clip_path = _clip_dir(event["id"])
    if clip_path.exists():
        shutil.rmtree(clip_path)
    clip_path.mkdir(parents=True, exist_ok=True)
    incident = {
        "event_id": event["id"],
        "zone_id": zone_id,
        "path": clip_path,
        "index": 0,
        "start_frame": frame_number,
        "last_occupied_frame": frame_number,
        "clear_frames": ZONE_CLEAR_SECONDS * CLIP_FPS,
        "classes": set(classes),
        "track_ids": set(occupancy["track_ids"]),
        "max_occupancy": len(detections),
        "best_confidence": best_detection.confidence,
    }
    for frame in buffered_frames:
        _append_clip_frame(incident, frame)
    _append_clip_frame(incident, current_frame)
    return incident


def _update_zone_incident(incident: dict, occupancy: dict, frame_number: int) -> None:
    detections = occupancy["detections"]
    incident["last_occupied_frame"] = frame_number
    incident["clear_frames"] = ZONE_CLEAR_SECONDS * CLIP_FPS
    incident["classes"].update(occupancy["classes"])
    incident["track_ids"].update(occupancy["track_ids"])
    incident["max_occupancy"] = max(incident["max_occupancy"], len(detections))
    if detections:
        incident["best_confidence"] = max(incident["best_confidence"], max(item.confidence for item in detections))


def _finalize_zone_incident(incident: dict, frame_number: int) -> None:
    duration = max(0, (frame_number - incident["start_frame"]) / CLIP_FPS)
    DEMO_EVENTS.update_metadata(
        incident["event_id"],
        status="closed",
        end_frame=frame_number,
        duration_seconds=round(duration, 2),
        object_classes=sorted(incident["classes"]),
        track_ids=sorted(incident["track_ids"]),
        max_occupancy=incident["max_occupancy"],
        clip_status="ready",
        clip_frame_count=incident["index"],
    )


def _annotated_frames(session_id: str, path: Path):
    capture = cv2.VideoCapture(str(path))
    detector = Detector(model_path="yolov8s.pt", confidence=0.3, image_size=960, tracker=str(Path(__file__).parents[1] / "bytetrack.yaml"))
    frame_number = 0
    tracked_detections = []
    frame_buffer = deque(maxlen=CLIP_PRE_SECONDS * CLIP_FPS)
    active_incidents: dict[str, dict] = {}
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_number % 3 == 0:
                tracked_detections = detector.track(frame)
            frame_number += 1
            current_zones = SESSION_ZONES.get(session_id, {})
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
            _draw_zones(frame, session_id)
            occupancy_by_zone = _zone_occupancy(current_zones, tracked_detections)
            for zone_id, incident in list(active_incidents.items()):
                _append_clip_frame(incident, frame)
                occupancy = occupancy_by_zone.get(zone_id, {"detections": [], "classes": set(), "track_ids": set()})
                if occupancy["detections"]:
                    _update_zone_incident(incident, occupancy, frame_number)
                else:
                    incident["clear_frames"] -= 1
                    if incident["clear_frames"] <= 0:
                        _finalize_zone_incident(incident, frame_number)
                        del active_incidents[zone_id]
            for zone_id, occupancy in occupancy_by_zone.items():
                if occupancy["detections"] and zone_id not in active_incidents:
                    active_incidents[zone_id] = _start_zone_incident(session_id, zone_id, occupancy, list(frame_buffer), frame, path, frame_number)
            frame_buffer.append(frame.copy())
            counts["total"] = sum(counts[key] for key in ("person", "car", "motorcycle", "bus", "truck"))
            SESSION_COUNTS[session_id] = counts.copy()
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
    finally:
        for incident in active_incidents.values():
            _finalize_zone_incident(incident, frame_number)
        capture.release()


@router.get("/api/stream/{session_id}")
def stream(session_id: str):
    camera = CAMERAS.get_camera(session_id)
    if not camera:
        raise HTTPException(404, "upload session not found")
    SESSION_ZONES[session_id] = {zone["id"]: zone["polygon"] for zone in camera.get("zones", [])}
    return StreamingResponse(_annotated_frames(session_id, Path(camera["path"])), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/counts/{session_id}")
def counts(session_id: str):
    if session_id not in SESSION_COUNTS and not CAMERAS.get_camera(session_id):
        raise HTTPException(404, "upload session not found")
    SESSION_COUNTS.setdefault(session_id, {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0})
    return SESSION_COUNTS[session_id]


@router.post("/api/reset/{session_id}")
def reset_counts(session_id: str):
    if session_id not in SESSION_COUNTS:
        raise HTTPException(404, "upload session not found")
    SESSION_COUNTS[session_id] = {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0}
    return SESSION_COUNTS[session_id]


@router.get("/api/events/{event_id}/clip")
def event_clip(event_id: int):
    frame = _clip_dir(event_id) / "frame-0000.jpg"
    if not frame.is_file():
        raise HTTPException(404, "event clip is still recording or unavailable")
    return FileResponse(frame, media_type="image/jpeg")


@router.get("/api/events/{event_id}/clip/meta")
def event_clip_meta(event_id: int):
    clip = _clip_dir(event_id)
    frames = sorted(clip.glob("frame-*.jpg")) if clip.is_dir() else []
    if not frames:
        raise HTTPException(404, "event clip is still recording or unavailable")
    return JSONResponse({"event_id": event_id, "fps": CLIP_FPS, "frame_count": len(frames)})


@router.get("/api/events/{event_id}/clip/frames/{frame_index}")
def event_clip_frame(event_id: int, frame_index: int):
    frame = _clip_dir(event_id) / f"frame-{frame_index:04d}.jpg"
    if not frame.is_file():
        raise HTTPException(404, "event clip frame not found")
    return FileResponse(frame, media_type="image/jpeg")
