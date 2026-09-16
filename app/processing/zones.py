from shapely.geometry import Point, Polygon

VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}

def occupancy(zones, detections):
    """Return the current occupancy for each polygon zone.

    Occupancy uses the bottom-center of each bounding box, which is generally
    more useful for surveillance zones than the box centroid. The result is
    deliberately state-free so it can be used by both live and uploaded-video
    processing loops.
    """
    result = {
        zone_id: {"detections": [], "classes": set(), "track_ids": set()}
        for zone_id in zones
    }
    polygons = {
        zone_id: Polygon(points)
        for zone_id, points in zones.items()
        if len(points) >= 3
    }
    for detection in detections:
        x1, _y1, x2, y2 = detection.bbox
        point = Point((x1 + x2) / 2, y2)
        for zone_id, polygon in polygons.items():
            if polygon.covers(point):
                result[zone_id]["detections"].append(detection)
                result[zone_id]["classes"].add(detection.object_class)
                if detection.track_id is not None:
                    result[zone_id]["track_ids"].add(detection.track_id)
    return result

def incident_summary(classes):
    """Return a stable human-readable summary for occupied zone classes."""
    has_person = "person" in classes
    has_vehicle = bool(classes & VEHICLE_CLASSES)
    if has_person and has_vehicle:
        return "person + vehicle"
    if has_vehicle:
        return "vehicle"
    if has_person:
        return "person"
    return "object"
