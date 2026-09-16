"""Business operations for configured camera zones."""


def list_zones(zones):
    return {camera_id: list(camera_zones.values()) for camera_id, camera_zones in zones.items()}


def create_zone(zones, camera_store, camera_id, zone):
    if camera_id in zones:
        if zone.id in zones[camera_id]:
            raise ValueError("zone already exists")
        zones[camera_id][zone.id] = zone
    else:
        camera = camera_store.get_camera(camera_id)
        if not camera or camera.get("source_type") != "upload":
            raise KeyError("camera not found")
        if any(saved["id"] == zone.id for saved in camera_store.list_zones(camera_id)):
            raise ValueError("zone already exists")
    camera_store.add_zone(camera_id, zone.id, zone.polygon)
    return zone


def remove_zone(zones, camera_store, camera_id, zone_id):
    if camera_id in zones:
        if zone_id not in zones[camera_id]:
            raise KeyError("zone not found")
        del zones[camera_id][zone_id]
    elif not any(saved["id"] == zone_id for saved in camera_store.list_zones(camera_id)):
        raise KeyError("zone not found")
    camera_store.delete_zone(camera_id, zone_id)
