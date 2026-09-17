from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.config import ZoneConfig
from ..services import zone as zone_service

router = APIRouter(prefix="/zones", tags=["zones"])


class ZoneRequest(BaseModel):
    camera_id: str
    zone: ZoneConfig


@router.get("")
def get_zones(request: Request):
    return zone_service.list_zones(request.app.state.zones)


@router.post("", status_code=201)
def add_zone(request: ZoneRequest, http_request: Request):
    try:
        return zone_service.create_zone(http_request.app.state.zones, http_request.app.state.camera_store, request.camera_id, request.zone)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip('"')) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/{camera_id}/{zone_id}", status_code=204)
def delete_zone(camera_id: str, zone_id: str, request: Request):
    try:
        zone_service.remove_zone(request.app.state.zones, request.app.state.camera_store, camera_id, zone_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
