from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..services import surveillance

router = APIRouter()


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
    try:
        return surveillance.upload_session(file.filename or "video.mp4", file.file)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/api/events")
def truncate_events():
    return {"deleted": surveillance.truncate_events()}


@router.get("/api/cameras")
def list_uploaded_cameras():
    return surveillance.list_cameras()


@router.delete("/api/cameras/{session_id}", status_code=204)
def delete_uploaded_camera(session_id: str):
    if surveillance.delete_session(session_id) is None:
        raise HTTPException(404, "camera not found")


def register_session_zone(session_id, zone_id, polygon):
    surveillance.register_zone(session_id, zone_id, polygon)


def unregister_session_zone(session_id, zone_id):
    surveillance.unregister_zone(session_id, zone_id)


@router.get("/api/stream/{session_id}")
def stream(session_id: str):
    camera = surveillance.get_camera(session_id)
    if not camera:
        raise HTTPException(404, "upload session not found")

    surveillance.SESSION_ZONES[session_id] = {
        zone["id"]: zone["polygon"]
        for zone in camera.get("zones", [])
    }

    return StreamingResponse(
        surveillance.stream_frames(session_id, Path(camera["path"])),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/api/stream/{session_id}/stop")
def stop_stream(session_id: str):
    if not surveillance.get_camera(session_id):
        raise HTTPException(404, "upload session not found")

    stopped = surveillance.stop_stream(session_id)
    return {
        "session_id": session_id,
        "stopped": stopped,
        "message": "stream stopping; active events will be finalized",
    }


@router.get("/api/counts/{session_id}")
def counts(session_id: str):
    if (
        session_id not in surveillance.SESSION_COUNTS
        and not surveillance.get_camera(session_id)
    ):
        raise HTTPException(404, "upload session not found")
    surveillance.SESSION_COUNTS.setdefault(session_id, surveillance.initial_counts())
    return surveillance.SESSION_COUNTS[session_id]


@router.post("/api/reset/{session_id}")
def reset_counts(session_id: str):
    if session_id not in surveillance.SESSION_COUNTS:
        raise HTTPException(404, "upload session not found")
    surveillance.SESSION_COUNTS[session_id] = surveillance.initial_counts()
    return surveillance.SESSION_COUNTS[session_id]


@router.get("/api/events/{event_id}/clip")
def event_clip(event_id: int):
    frame = surveillance.CLIPS / f"event-{event_id}" / "frame-0000.jpg"
    if not frame.is_file():
        raise HTTPException(404, "event clip is still recording or unavailable")
    return FileResponse(frame, media_type="image/jpeg")


@router.get("/api/events/{event_id}/clip/meta")
def event_clip_meta(event_id: int):
    clip = surveillance.CLIPS / f"event-{event_id}"
    frames = sorted(clip.glob("frame-*.jpg")) if clip.is_dir() else []
    if not frames:
        raise HTTPException(404, "event clip is still recording or unavailable")
    return JSONResponse(
        {
            "event_id": event_id,
            "fps": surveillance.event_clip_fps(event_id),
            "frame_count": len(frames),
        }
    )


@router.get("/api/events/{event_id}/clip/frames/{frame_index}")
def event_clip_frame(event_id: int, frame_index: int):
    frame = surveillance.CLIPS / f"event-{event_id}" / f"frame-{frame_index:04d}.jpg"
    if not frame.is_file():
        raise HTTPException(404, "event clip frame not found")
    return FileResponse(frame, media_type="image/jpeg")
