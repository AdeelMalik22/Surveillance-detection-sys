# Project guidance

## Overview

This repository is an AI surveillance MVP built with FastAPI, OpenCV, Ultralytics YOLO/ByteTrack, Shapely, SQLite, and a small browser dashboard.

## Architecture

- `app/main.py`: FastAPI application, configured camera workers, snapshots, status, events, and configured-camera zones.
- `app/capture.py`: frame capture and camera reconnect logic.
- `app/detector.py`: YOLO detection and ByteTrack integration.
- `app/pipeline.py`: reusable capture-to-annotation processing loop.
- `app/zones.py`: shared polygon occupancy calculation and class summaries.
- `app/events.py`: SQLite event persistence.
- `app/services/surveillance.py`: uploaded-video workflow.
- `app/web/`: dashboard and upload/stream routes.

## Current limitation

The configured-camera path starts `CaptureWorker` instances but does not yet connect them to `Detector`, shared occupancy processing, or `EventStore`. The uploaded-video workflow now uses the shared occupancy calculation and incident semantics. The next major change is to connect the live pipeline to the same incident lifecycle. Avoid adding another independent processing path.

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
