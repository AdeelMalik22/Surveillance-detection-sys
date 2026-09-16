from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from .capture import CaptureWorker
from .config import Settings, ZoneConfig, load_settings
from .detector import Detector
from .events import EventStore
from .incidents import IncidentManager
from .pipeline import ProcessingPipeline
from .web.routes import register_session_zone, router as web_router, unregister_session_zone
from .zones import incident_summary, occupancy

settings: Settings = load_settings(); store = EventStore(settings.database); workers = {}; pipelines = {}; incidents = {}
zones = {camera.id: {zone.id: zone for zone in camera.zones} for camera in settings.cameras}


def _incident_callbacks(camera_id):
    def open_incident(zone_id, current, frame_number):
        best = max(current["detections"], key=lambda item: item.confidence)
        event = store.add(camera_id, zone_id, incident_summary(current["classes"]), best.confidence, best.bbox, {
            "event_type": "zone_occupancy", "grouping": "continuous_zone_occupancy", "status": "open",
            "start_frame": frame_number, "end_frame": None, "duration_seconds": None,
            "object_classes": sorted(current["classes"]), "track_ids": sorted(current["track_ids"]),
            "max_occupancy": len(current["detections"]),
        })
        return {"event_id": event["id"], "start_frame": frame_number,
                "last_occupied_frame": frame_number, "classes": set(current["classes"]),
                "track_ids": set(current["track_ids"]), "max_occupancy": len(current["detections"])}

    def update_incident(incident, current, frame_number):
        incident["last_occupied_frame"] = frame_number
        incident["classes"].update(current["classes"])
        incident["track_ids"].update(current["track_ids"])
        incident["max_occupancy"] = max(incident["max_occupancy"], len(current["detections"]))
        store.update_metadata(incident["event_id"], object_classes=sorted(incident["classes"]),
                              track_ids=sorted(incident["track_ids"]), max_occupancy=incident["max_occupancy"])

    def close_incident(incident, frame_number):
        store.update_metadata(incident["event_id"], status="closed", end_frame=frame_number,
                              duration_seconds=round(max(0, (frame_number - incident["start_frame"]) / settings.target_fps), 2),
                              object_classes=sorted(incident["classes"]), track_ids=sorted(incident["track_ids"]),
                              max_occupancy=incident["max_occupancy"])

    return open_incident, update_incident, close_incident

@asynccontextmanager
async def lifespan(_):
    for camera in settings.cameras:
        # Each tracker keeps camera-local identities; sharing a persistent
        # tracker across cameras would allow IDs to leak between streams.
        detector = Detector(model_path=settings.model, confidence=settings.confidence, device=settings.device, image_size=settings.image_size)
        worker = CaptureWorker(camera.id, camera.url, settings.target_fps)
        open_incident, update_incident, close_incident = _incident_callbacks(camera.id)
        incident_manager = IncidentManager(
            clear_frames=max(1, round(5 * settings.target_fps)),
            on_open=open_incident,
            on_update=update_incident,
            on_close=close_incident,
        )
        incidents[camera.id] = incident_manager
        pipelines[camera.id] = ProcessingPipeline(
            worker,
            detector,
            settings.target_fps,
            on_detections=lambda detections, frame, frame_number, camera_id=camera.id: incidents[camera_id].process(
                occupancy({zone_id: zone.polygon for zone_id, zone in zones.get(camera_id, {}).items()}, detections),
                frame,
                frame_number,
            ),
        )
        workers[camera.id] = worker
        worker.start(); pipelines[camera.id].start()
    yield
    for pipeline in pipelines.values(): pipeline.stop()
    for camera_id, worker in workers.items():
        incidents[camera_id].close_all(pipelines[camera_id].frame_number)
        worker.stop()

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
    pipeline = pipelines.get(camera_id)
    if not pipeline or pipeline.latest_annotated() is None: raise HTTPException(404, "no snapshot available")
    import cv2
    ok, encoded = cv2.imencode(".jpg", pipeline.latest_annotated())
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
    zones[request.camera_id][request.zone.id] = request.zone
    register_session_zone(request.camera_id, request.zone.id, request.zone.polygon)
    return request.zone

@app.delete("/zones/{camera_id}/{zone_id}", status_code=204)
def delete_zone(camera_id: str, zone_id: str):
    if zone_id not in zones.get(camera_id, {}): raise HTTPException(404, "zone not found")
    del zones[camera_id][zone_id]
    unregister_session_zone(camera_id, zone_id)
