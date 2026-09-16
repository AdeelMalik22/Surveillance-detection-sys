from __future__ import annotations
import os, re
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, field_validator

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

class ZoneConfig(BaseModel):
    id: str
    polygon: list[list[float]] = Field(min_length=3)
    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, value):
        if any(len(point) != 2 for point in value): raise ValueError("polygon points must be [x, y]")
        return value

class CameraConfig(BaseModel):
    id: str
    url: str
    zones: list[ZoneConfig] = []

class Settings(BaseModel):
    model: str = "yolov8n.pt"
    device: str = "auto"
    confidence: float = Field(0.3, ge=0, le=1)
    image_size: int = Field(960, ge=320, le=1920)
    target_fps: float = Field(8, gt=0, le=60)
    zone_point: str = "bottom_center"
    database: str = "events.db"
    cameras: list[CameraConfig] = []
    @field_validator("zone_point")
    @classmethod
    def valid_point(cls, value):
        if value not in {"centroid", "bottom_center"}: raise ValueError("zone_point must be centroid or bottom_center")
        return value

def _expand(value):
    if isinstance(value, str): return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict): return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list): return [_expand(v) for v in value]
    return value

def load_settings(path="config.yaml"):
    # Resolve the default project config from the repository root, rather than
    # depending on the directory from which Uvicorn was launched.
    file = Path(path)
    if path == "config.yaml" and not file.is_absolute():
        file = Path(__file__).parents[2] / path
    if not file.exists(): return Settings()
    with file.open(encoding="utf-8") as handle: data = yaml.safe_load(handle) or {}
    return Settings.model_validate(_expand(data))
