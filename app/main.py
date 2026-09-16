from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .processing.capture import CaptureWorker
from .core.config import Settings, ZoneConfig, load_settings
from .processing.detector import Detector
from .infrastructure.events import CameraStore, EventStore
from .processing.incidents import IncidentManager
from .processing.pipeline import ProcessingPipeline
from .web.routes import router as web_router
from .processing.zones import incident_summary, occupancy
from .services import surveillance
from .api.camera import router as camera_router
from .api.event import router as event_router
from .api.system import router as system_router
from .api.zone import router as zone_router

settings: Settings = load_settings(); store = EventStore(settings.database); camera_store = CameraStore(store.db)
# Keep uploaded-video and configured-camera workflows on the same database.
surveillance.DEMO_EVENTS = store
surveillance.CAMERAS = camera_store
workers = {}; pipelines = {}; incidents = {}
zones = {camera.id: {} for camera in settings.cameras}


def _load_camera_configuration():
    """Persist configured cameras and merge their saved zones with YAML zones."""
    for camera in settings.cameras:
        camera_store.add_camera(camera.id, camera.id, camera.url, camera.url, source_type="live")
        saved_zones = camera_store.list_zones(camera.id)
        configured = {zone.id: zone for zone in camera.zones}
        for saved in saved_zones:
            configured[saved["id"]] = ZoneConfig(id=saved["id"], polygon=saved["polygon"])
        zones[camera.id] = configured


_load_camera_configuration()


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
# Store configuration and persistence handles immediately. Worker collections
# are populated by lifespan, but API handlers can safely access the store even
# while camera startup is still in progress.
app.state.settings = settings
app.state.store = store
app.state.camera_store = camera_store
app.state.workers = workers
app.state.pipelines = pipelines
app.state.zones = zones
app.include_router(web_router)
app.include_router(system_router)
app.include_router(event_router)
app.include_router(zone_router)
app.include_router(camera_router)
