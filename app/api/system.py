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
    return {"model": settings.model, "cameras": [worker.status.__dict__ for worker in request.app.state.workers.values()]}


@router.get("/cameras/{camera_id}/snapshot")
def snapshot(camera_id: str, request: Request):
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
    if camera_id not in request.app.state.pipelines:
        raise HTTPException(404, "camera not found")

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
