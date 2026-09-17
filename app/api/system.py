from pathlib import Path
import time

import cv2
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

router = APIRouter()


@router.get("/health")
def health(request: Request):
    settings = request.app.state.settings
    return {"status": "ok", "model": settings.model, "model_loaded": Path(settings.model).exists()}


@router.get("/status")
def status(request: Request):
    settings = request.app.state.settings
    cameras = []
    for camera_id, worker in request.app.state.workers.items():
        capture_status = worker.status
        last_frame_age = None
        if capture_status.last_frame_at is not None:
            last_frame_age = round(max(0, time.time() - capture_status.last_frame_at), 2)
        pipeline = request.app.state.pipelines.get(camera_id)
        cameras.append({
            "camera_id": camera_id,
            "connected": capture_status.connected,
            "capture_fps": round(capture_status.capture_fps, 2),
            "inference_fps": round(pipeline.inference_fps, 2) if pipeline else 0.0,
            "last_error": capture_status.last_error,
            "last_frame_age_seconds": last_frame_age,
        })
    return {"model": settings.model, "cameras": cameras}


@router.get("/cameras/{camera_id}/snapshot")
def snapshot(camera_id: str, request: Request):
    worker = request.app.state.workers.get(camera_id)
    if worker is None:
        raise HTTPException(404, "camera not found")
    if not worker.status.connected:
        raise HTTPException(503, "camera is unavailable")
    pipeline = request.app.state.pipelines.get(camera_id)
    frame = pipeline.latest_annotated() if pipeline else None
    if frame is None:
        raise HTTPException(404, "no snapshot available")
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(500, "snapshot encoding failed")
    return Response(encoded.tobytes(), media_type="image/jpeg")


@router.get("/cameras/{camera_id}/stream")
def stream(camera_id: str, request: Request):
    worker = request.app.state.workers.get(camera_id)
    if worker is None:
        raise HTTPException(404, "camera not found")
    if not worker.status.connected:
        raise HTTPException(503, "camera is unavailable")

    def frames():
        pipeline = request.app.state.pipelines[camera_id]
        while True:
            frame = pipeline.latest_annotated()
            if frame is None:
                time.sleep(0.1)
                continue
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
            time.sleep(0.1)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")
