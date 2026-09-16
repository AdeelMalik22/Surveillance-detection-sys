# Project guidance

## Overview

This repository is an AI surveillance MVP built with FastAPI, OpenCV, Ultralytics YOLO/ByteTrack, Shapely, SQLite, and a small browser dashboard.

## Architecture

- `app/main.py`: FastAPI application, configured camera workers, snapshots, status, events, and configured-camera zones.
- `app/api/`: HTTP route modules; keep endpoint handlers thin and organized by resource (`zone.py`, `event.py`, `camera.py`, `system.py`).
- `app/processing/`: frame capture, YOLO/ByteTrack detection, pipeline orchestration, shared zone occupancy, and incident lifecycle. Tracking is provided by Ultralytics inside `detector.py`; do not add a second custom tracker.
- `app/core/config.py`: application settings, YAML loading, and configuration models.
- `app/infrastructure/events.py`: SQLite event and camera/zone persistence.
- `app/events.py`: SQLite event persistence.
- `app/services/zone.py`: zone API business operations.
- `app/services/events.py`: event API business operations.
- `app/services/surveillance.py`: uploaded-video workflow.
- `app/web/`: dashboard and upload/stream routes.

## Current limitation

The configured-camera path now connects `CaptureWorker`, `ProcessingPipeline`, `Detector`, shared occupancy processing, `IncidentManager`, and `EventStore`. The existing `CameraStore` persists configured cameras and live zones. The uploaded-video workflow uses the same occupancy and incident semantics. The next major work is adding end-to-end live event tests. Avoid adding another independent processing path.

## Development rules

- Preserve existing user changes; do not use destructive Git operations.
- Keep RTSP credentials and raw video out of logs and source control.
- Keep business logic in shared, testable services rather than route handlers.
- Every new API belongs under `app/api/<resource>.py` and delegates business logic to `app/services/<resource>.py`.
- Keep configuration models in `app/core/` and database/external-system adapters in `app/infrastructure/`.
- Persist camera and zone configuration instead of relying on process-global dictionaries.
- Add or update tests for detection, tracking, zones, events, and API behavior.
- Use UTC timestamps for persisted events.
- Stop long-running workers and release OpenCV resources cleanly.
- Run `pytest` after relevant changes.

## Commands

```bash
pytest
uvicorn main:app --reload
```
