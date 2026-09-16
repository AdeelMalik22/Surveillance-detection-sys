"""Business operations for configured camera zones."""


def list_zones(zones):
    return {camera_id: list(camera_zones.values()) for camera_id, camera_zones in zones.items()}


def create_zone(zones, camera_store, camera_id, zone):
    if camera_id not in zones:
        raise KeyError("camera not found")
    if zone.id in zones[camera_id]:
        raise ValueError("zone already exists")
    zones[camera_id][zone.id] = zone
    camera_store.add_zone(camera_id, zone.id, zone.polygon)
    return zone


def remove_zone(zones, camera_store, camera_id, zone_id):
    if zone_id not in zones.get(camera_id, {}):
        raise KeyError("zone not found")
    del zones[camera_id][zone_id]
    camera_store.delete_zone(camera_id, zone_id)
