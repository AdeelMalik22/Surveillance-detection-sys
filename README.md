# AI Surveillance MVP

FastAPI-based surveillance MVP for local videos and RTSP sources. The project includes video capture, YOLO detection, Ultralytics ByteTrack tracking, polygon zones, SQLite event storage, and a browser dashboard.

## Current status

The uploaded-video workflow is the most complete path. It supports video upload and session management, YOLO detection for people and vehicles, ByteTrack tracking, shared polygon-zone occupancy detection, continuous incidents, SQLite events, event frame sequences, and an MJPEG browser stream.

The configured-camera API now runs capture, YOLO/ByteTrack processing, shared zone occupancy, continuous incidents, and SQLite event persistence. Its snapshot endpoint returns the latest annotated frame. Camera definitions and zones are stored through the existing SQLite `CameraStore`, so API-created zones survive application restarts.

## Next phase

Connect the live camera path:

```text
CaptureWorker -> Detector.track() -> ZoneEngine -> EventStore -> annotated output
```

The occupancy calculation is shared in `app/zones.py`, and the continuous open/update/close lifecycle is shared in `app/incidents.py`. Both uploaded videos and configured cameras use this manager and close incidents after five seconds of absence. The remaining integration work is to add end-to-end live event tests. Production hardening should then address authentication, restricted CORS, resource cleanup, structured logging, model lifecycle management, and concurrent database access.

## Setup

Use a stable Python 3.11 release for PyTorch.

```bash
cp config.example.yaml config.yaml
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for API documentation or `http://127.0.0.1:8000/ui` for the dashboard. The root `main.py` starts the FastAPI application from `app.main`. A local `.mp4` path can be used as a camera URL in `config.yaml`.

## Useful commands

```bash
pytest
python scripts/test_capture.py --source sample.mp4 --seconds 20
python scripts/test_detection.py --source sample.mp4 --seconds 20 --output annotated.jpg
```

## Configuration

Copy `config.example.yaml` to `config.yaml`. Settings include model path, confidence threshold, inference size, target FPS, database path, cameras, and polygon zones. Environment variables can be referenced as `${VARIABLE_NAME}` in YAML values.

Supported detection classes are `person`, `car`, `motorcycle`, `bus`, and `truck`.

## Privacy and security

Do not log RTSP credentials or persist raw video by default. Before deployment, add authentication, restrict CORS, validate upload size and type, protect event media, and follow applicable surveillance and privacy laws.
