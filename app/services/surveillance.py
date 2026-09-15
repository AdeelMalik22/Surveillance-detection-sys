"""Business logic for uploaded-video surveillance sessions."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from collections import deque
from pathlib import Path

import cv2
from shapely.geometry import Point, Polygon

from ..detector import Detector
from ..events import CameraStore, EventStore

UPLOADS = Path(tempfile.gettempdir()) / "surveillance-mvp-uploads"
CLIPS = Path(tempfile.gettempdir()) / "surveillance-mvp-event-clips"
UPLOADS.mkdir(parents=True, exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)
SESSION_COUNTS: dict[str, dict[str, int]] = {}
SESSION_ZONES: dict[str, dict[str, list[list[float]]]] = {}
DEMO_EVENTS = EventStore()
CAMERAS = CameraStore(DEMO_EVENTS.db)
CLIP_FPS = 8
CLIP_PRE_SECONDS = 2
ZONE_CLEAR_SECONDS = 5
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}


def initial_counts():
    return {"person": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "total": 0}


def upload_session(filename: str, source) -> dict:
    suffix = Path(filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise ValueError("upload a supported video file")
    session_id = uuid.uuid4().hex
    destination = UPLOADS / f"{session_id}{suffix}"
    with destination.open("wb") as output:
        shutil.copyfileobj(source, output)
    SESSION_COUNTS[session_id] = initial_counts()
    SESSION_ZONES[session_id] = {}
    return CAMERAS.add_camera(session_id, filename, str(destination), f"/api/stream/{session_id}")


def delete_session(session_id: str):
    path = CAMERAS.delete_camera(session_id)
    if path is None:
        return None
    SESSION_COUNTS.pop(session_id, None)
    SESSION_ZONES.pop(session_id, None)
    file_path = Path(path)
    if file_path.is_file():
        file_path.unlink()
    return path


def register_zone(session_id, zone_id, polygon):
    if CAMERAS.get_camera(session_id):
        SESSION_COUNTS.setdefault(session_id, initial_counts())
        SESSION_ZONES.setdefault(session_id, {})[zone_id] = polygon
        CAMERAS.add_zone(session_id, zone_id, polygon)


def unregister_zone(session_id, zone_id):
    SESSION_ZONES.get(session_id, {}).pop(zone_id, None)
    CAMERAS.delete_zone(session_id, zone_id)


def list_cameras():
    cameras = CAMERAS.list_cameras()
    for camera in cameras:
        SESSION_COUNTS.setdefault(camera["session_id"], initial_counts())
        SESSION_ZONES[camera["session_id"]] = {z["id"]: z["polygon"] for z in camera.get("zones", [])}
    return cameras


def get_camera(session_id):
    return CAMERAS.get_camera(session_id)


def _draw_zones(frame, session_id):
    for zone_id, polygon in SESSION_ZONES.get(session_id, {}).items():
        if len(polygon) < 3:
            continue
        points = [(int(x), int(y)) for x, y in polygon]
        for start, end in zip(points, points[1:] + points[:1]):
            cv2.line(frame, start, end, (116, 223, 187), 2)
        x, y = points[0]
        cv2.putText(frame, zone_id, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (116, 223, 187), 2)


def _zone_occupancy(zones, detections):
    occupancy = {z: {"detections": [], "classes": set(), "track_ids": set()} for z in zones}
    polygons = {z: Polygon(points) for z, points in zones.items() if len(points) >= 3}
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


def _append_clip_frame(clip, frame):
    path = clip["path"] / f"frame-{clip['index']:04d}.jpg"
    ok, encoded = cv2.imencode(".jpg", frame)
    if ok:
        path.write_bytes(encoded.tobytes())
        clip["index"] += 1


def _summary(classes):
    person, vehicle = "person" in classes, bool(classes & VEHICLE_CLASSES)
    return "person + vehicle" if person and vehicle else "vehicle" if vehicle else "person" if person else "object"


def _start_incident(session_id, zone_id, occupancy, buffered, frame, source, number):
    detections = occupancy["detections"]
    best = max(detections, key=lambda item: item.confidence)
    event = DEMO_EVENTS.add(session_id, zone_id, _summary(occupancy["classes"]), best.confidence, best.bbox, {
        "event_type": "zone_occupancy", "grouping": "continuous_zone_occupancy", "status": "open",
        "start_frame": number, "end_frame": None, "duration_seconds": None, "source_video": source.name,
        "object_classes": sorted(occupancy["classes"]), "track_ids": sorted(occupancy["track_ids"]),
        "max_occupancy": len(detections), "clip_status": "recording", "clip_type": "image_sequence",
        "clip_fps": CLIP_FPS, "clip_frame_count": 0, "clip_url": "/api/events/{event_id}/clip",
    })
    DEMO_EVENTS.update_metadata(event["id"], clip_url=f"/api/events/{event['id']}/clip")
    clip_path = CLIPS / f"event-{event['id']}"
    if clip_path.exists(): shutil.rmtree(clip_path)
    clip_path.mkdir(parents=True)
    incident = {"event_id": event["id"], "path": clip_path, "index": 0, "start_frame": number,
                "last_occupied_frame": number, "clear_frames": ZONE_CLEAR_SECONDS * CLIP_FPS,
                "classes": set(occupancy["classes"]), "track_ids": set(occupancy["track_ids"]),
                "max_occupancy": len(detections)}
    for item in buffered: _append_clip_frame(incident, item)
    _append_clip_frame(incident, frame)
    return incident


def _update_incident(incident, occupancy, number):
    incident["last_occupied_frame"] = number
    incident["classes"].update(occupancy["classes"])
    incident["track_ids"].update(occupancy["track_ids"])
    incident["max_occupancy"] = max(incident["max_occupancy"], len(occupancy["detections"]))


def _finalize_incident(incident, number):
    DEMO_EVENTS.update_metadata(incident["event_id"], status="closed", end_frame=number,
        duration_seconds=round(max(0, (number - incident["start_frame"]) / CLIP_FPS), 2),
        object_classes=sorted(incident["classes"]), track_ids=sorted(incident["track_ids"]),
        max_occupancy=incident["max_occupancy"], clip_status="ready", clip_frame_count=incident["index"])


def stream_frames(session_id, path):
    capture = cv2.VideoCapture(str(path))
    detector = Detector(model_path="yolov8s.pt", confidence=0.3, image_size=960,
                        tracker=str(Path(__file__).parents[1] / "bytetrack.yaml"))
    number, detections = 0, []
    buffer, active = deque(maxlen=CLIP_PRE_SECONDS * CLIP_FPS), {}
    try:
        while True:
            ok, frame = capture.read()
            if not ok: break
            if number % 3 == 0: detections = detector.track(frame)
            number += 1
            zones = SESSION_ZONES.get(session_id, {})
            counts = initial_counts()
            for detection in detections:
                if detection.object_class in counts: counts[detection.object_class] += 1
                x1, y1, x2, y2 = map(int, detection.bbox)
                color = (0, 0, 255) if detection.object_class in {"car", "truck"} else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{detection.object_class} #{detection.track_id or '?'} {detection.confidence:.2f}", (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
            _draw_zones(frame, session_id)
            occupancy = _zone_occupancy(zones, detections)
            for zone_id, incident in list(active.items()):
                _append_clip_frame(incident, frame)
                current = occupancy.get(zone_id, {"detections": [], "classes": set(), "track_ids": set()})
                if current["detections"]: _update_incident(incident, current, number)
                elif number - incident["last_occupied_frame"] >= incident["clear_frames"]:
                    _finalize_incident(incident, number); del active[zone_id]
            for zone_id, current in occupancy.items():
                if current["detections"] and zone_id not in active:
                    active[zone_id] = _start_incident(session_id, zone_id, current, list(buffer), frame, path, number)
            buffer.append(frame.copy())
            counts["total"] = sum(counts[k] for k in ("person", "car", "motorcycle", "bus", "truck"))
            SESSION_COUNTS[session_id] = counts
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok: yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
    finally:
        for incident in active.values(): _finalize_incident(incident, number)
        capture.release()


def truncate_events():
    row = DEMO_EVENTS.db.execute("SELECT COUNT(*) AS count FROM events").fetchone()
    deleted = int(row["count"])
    DEMO_EVENTS.db.execute("DELETE FROM events"); DEMO_EVENTS.db.commit()
    for path in CLIPS.glob("event-*"):
        if path.is_dir(): shutil.rmtree(path)
    return deleted
