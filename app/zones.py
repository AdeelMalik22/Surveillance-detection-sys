from dataclasses import dataclass
from shapely.geometry import Point, Polygon

@dataclass
class Detection:
    object_class: str
    confidence: float
    bbox: list[float]
    track_id: int

class ZoneEngine:
    def __init__(self, zones, point_mode="bottom_center"):
        self.zones = {zone_id: Polygon(points) for zone_id, points in zones.items()}; self.point_mode = point_mode; self.inside = set()
    def entries(self, detections):
        current, entries = set(), []
        for detection in detections:
            x1, y1, x2, y2 = detection.bbox; point = Point((x1+x2)/2, (y1+y2)/2) if self.point_mode == "centroid" else Point((x1+x2)/2, y2)
            for zone_id, polygon in self.zones.items():
                key = (detection.track_id, zone_id)
                if polygon.covers(point):
                    current.add(key)
                    if key not in self.inside: entries.append((detection, zone_id))
        self.inside = current; return entries
