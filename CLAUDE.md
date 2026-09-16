# Project guidance

## Overview

This repository is an AI surveillance MVP built with FastAPI, OpenCV, Ultralytics YOLO/ByteTrack, Shapely, SQLite, and a small browser dashboard.

## Architecture

- `app/main.py`: FastAPI application, configured camera workers, snapshots, status, events, and configured-camera zones.
- `app/capture.py`: frame capture and camera reconnect logic.
- `app/detector.py`: YOLO detection and ByteTrack integration.
- `app/pipeline.py`: reusable capture-to-annotation processing loop.
- `app/zones.py`: shared polygon occupancy calculation and class summaries.
- `app/incidents.py`: shared continuous incident lifecycle manager.
- `app/events.py`: SQLite event persistence.
- `app/services/surveillance.py`: uploaded-video workflow.
- `app/web/`: dashboard and upload/stream routes.

## Current limitation

The configured-camera path now connects `CaptureWorker`, `ProcessingPipeline`, `Detector`, shared occupancy processing, `IncidentManager`, and `EventStore`. The uploaded-video workflow uses the same occupancy and incident semantics. The next major work is persisting live camera zones and adding end-to-end live event tests. Avoid adding another independent processing path.

## Development rules

- Preserve existing user changes; do not use destructive Git operations.
- Keep RTSP credentials and raw video out of logs and source control.
- Keep business logic in shared, testable services rather than route handlers.
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
