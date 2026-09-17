from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.event import router as event_router
from app.api.system import router as system_router
from app.api.zone import router as zone_router
from app.core.config import Settings, ZoneConfig
from app.infrastructure.events import CameraStore, EventStore


def make_client(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    camera_store = CameraStore(store.db)
    camera_store.add_camera("camera-1", "Camera 1", "rtsp://example.test/stream", "rtsp://example.test/stream", source_type="live")

    app = FastAPI()
    app.include_router(system_router)
    app.include_router(event_router)
    app.include_router(zone_router)
    app.state.settings = Settings(model="test-model.pt")
    app.state.store = store
    app.state.camera_store = camera_store
    app.state.workers = {"camera-1": SimpleNamespace(status=SimpleNamespace(camera_id="camera-1", connected=False))}
    app.state.pipelines = {}
    app.state.zones = {"camera-1": {}}
    return TestClient(app), store


def test_system_event_and_zone_api_endpoints(tmp_path):
    client, store = make_client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/status")
    assert status.status_code == 200
    assert status.json()["cameras"][0]["camera_id"] == "camera-1"

    assert client.get("/events").status_code == 200
    assert client.get("/zones").json() == {"camera-1": []}

    zone = {
        "camera_id": "camera-1",
        "zone": {"id": "restricted", "polygon": [[0, 0], [10, 0], [10, 10]]},
    }
    created = client.post("/zones", json=zone)
    assert created.status_code == 201
    assert created.json()["id"] == "restricted"

    duplicate = client.post("/zones", json=zone)
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    assert client.get("/zones").json()["camera-1"][0]["id"] == "restricted"
    assert client.delete("/zones/camera-1/restricted").status_code == 204
    assert client.get("/zones").json() == {"camera-1": []}

    store.db.close()
