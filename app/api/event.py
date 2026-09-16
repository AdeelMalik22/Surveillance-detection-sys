from fastapi import APIRouter, Query, Request
from ..services import events as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.delete("")
def truncate_events(request: Request):
    return {"deleted": event_service.clear_events(request.app.state.store)}


@router.get("")
def events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    camera_id: str | None = None,
    zone_id: str | None = None,
    object_class: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    return event_service.list_events(
        request.app.state.store,
        limit, offset, camera_id=camera_id, zone_id=zone_id,
        object_class=object_class, **{"from": from_, "to": to}
    )
