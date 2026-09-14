from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from .capture import CaptureWorker
from .config import Settings, ZoneConfig, load_settings
from .events import EventStore
from .web.routes import router as web_router

settings: Settings = load_settings(); store = EventStore(settings.database); workers = {}
zones = {camera.id: {zone.id: zone for zone in camera.zones} for camera in settings.cameras}

@asynccontextmanager
async def lifespan(_):
    for camera in settings.cameras:
        workers[camera.id] = CaptureWorker(camera.id, camera.url, settings.target_fps); workers[camera.id].start()
    yield
    for worker in workers.values(): worker.stop()

app = FastAPI(title="AI Surveillance MVP", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(web_router)

@app.get("/health")
def health(): return {"status": "ok", "model": settings.model, "model_loaded": Path(settings.model).exists()}

@app.get("/status")
def status(): return {"model": settings.model, "cameras": [worker.status.__dict__ for worker in workers.values()]}

@app.get("/events")
def events(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), camera_id: str | None = None, zone_id: str | None = None, object_class: str | None = None, from_: str | None = Query(None, alias="from"), to: str | None = None):
    return store.list(limit, offset, camera_id=camera_id, zone_id=zone_id, object_class=object_class, **{"from": from_, "to": to})

@app.get("/cameras/{camera_id}/snapshot")
def snapshot(camera_id: str):
    worker = workers.get(camera_id)
    if not worker or worker.latest() is None: raise HTTPException(404, "no snapshot available")
    import cv2
    ok, encoded = cv2.imencode(".jpg", worker.latest())
    if not ok: raise HTTPException(500, "snapshot encoding failed")
    return Response(encoded.tobytes(), media_type="image/jpeg")

class ZoneRequest(BaseModel):
    camera_id: str
    zone: ZoneConfig

@app.get("/zones")
def get_zones(): return {camera_id: list(camera_zones.values()) for camera_id, camera_zones in zones.items()}

@app.post("/zones", status_code=201)
def add_zone(request: ZoneRequest):
    if request.camera_id not in zones: zones[request.camera_id] = {}
    if request.zone.id in zones[request.camera_id]: raise HTTPException(409, "zone already exists")
    zones[request.camera_id][request.zone.id] = request.zone; return request.zone

@app.delete("/zones/{camera_id}/{zone_id}", status_code=204)
def delete_zone(camera_id: str, zone_id: str):
    if zone_id not in zones.get(camera_id, {}): raise HTTPException(404, "zone not found")
    del zones[camera_id][zone_id]
