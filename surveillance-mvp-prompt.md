# AI Surveillance MVP — Build Prompt (v2)

## Objective
Build a working MVP of an AI-based video surveillance system that detects **persons** and **vehicles** from live RTSP camera feeds using standard/existing IP cameras (no special AI camera hardware required — all intelligence lives in software), triggers a zone-based "intrusion" event when a person or vehicle enters a predefined polygonal zone, and exposes status/events via an API. Optimize for correctness and speed-to-demo, not production scale.

## Tech Stack (fixed for MVP)
- Python 3.11+
- OpenCV (`opencv-python`) — RTSP capture and frame handling
- Ultralytics YOLOv8 (or YOLOv11), pre-trained, no custom training — optionally managed/exported via [Ultralytics Platform](https://platform.ultralytics.com/) if we want hosted model management, training dashboards, or export tooling instead of pure local `ultralytics` package usage
- FastAPI + Uvicorn — backend API
- Shapely — polygon geometry for zone logic
- SQLite (or in-memory list for MVP) — event log storage

## Functional Requirements

### 1. RTSP Capture Module (`capture.py`)
- Connect to one or more RTSP streams from standard IP cameras using `cv2.VideoCapture`.
- Run capture in its own thread per camera so a slow/dead stream doesn't block inference.
- Downsample resolution (target ~640px width) and throttle to 5–10 FPS by dropping frames rather than processing every frame — running inference on full 60 FPS source video is unnecessary for security tracking and will bottleneck the MVP immediately.
- Auto-reconnect on stream drop (retry with backoff), and log connection state per camera.

### 2. Detection Module (`detector.py`)
- Load a pre-trained YOLOv8n or YOLOv8s model via `ultralytics` (or a model pulled from Ultralytics Platform if we go that route).
- Restrict inference to COCO classes: `person` (0) and vehicle classes (`car`, `motorcycle`, `bus`, `truck`).
- Return bounding boxes, class labels, and confidence scores per frame.
- Make confidence threshold configurable (default 0.5).

### 3. Zone / Event Logic (`zones.py`)
- Support defining one or more polygonal zones per camera (list of x,y points), loaded from a config file (JSON/YAML).
- For each detection, check if the box centroid (or bottom-center point) falls inside a zone using Shapely.
- Trigger an "event" only on **zone entry** (state transition from outside→inside) — for persons and vehicles both — not every frame the object remains inside; track object presence per zone to avoid duplicate/spam events.
- Each event record: `camera_id`, `zone_id`, `object_class`, `confidence`, `timestamp`, `bbox`.

### 4. Backend API (`main.py`, FastAPI)
- `GET /status` — camera connection status, current FPS, model info.
- `GET /events` — paginated event log, filterable by camera/zone/class/time range, so a frontend can request status updates and event logs asynchronously.
- `GET /cameras/{id}/snapshot` — latest annotated frame (JPEG) for that camera, for quick visual verification.
- `POST /zones` / `GET /zones` — CRUD for zone configuration (can be file-backed for MVP, no need for full DB layer).
- CORS enabled for local frontend testing.

### 5. Config
- Single `config.yaml` (or `.env` + `config.yaml`) defining: RTSP URLs, per-camera zones, target FPS, confidence threshold, model path.

## Non-Functional / Constraints
- No custom model training — pre-trained YOLO weights only.
- No GPU assumed available; code should run on CPU but be easy to switch to CUDA if present (`device` param).
- Keep it to a single-process app for MVP (no Celery/Kafka/message queue yet) — threads/asyncio are enough.
- Prioritize clear module boundaries (capture / detection / zone logic / API) over premature abstraction, since this will be iterated on.

## Deliverables
1. Working repo with the modules above, `requirements.txt`, and a `README.md` covering setup and how to point it at an RTSP stream (including a note on testing with a public/test RTSP stream or a local video file as a stand-in).
2. A minimal way to visually verify detection is working (e.g., a script or endpoint that saves/serves an annotated frame with boxes and zone overlay drawn).
3. Basic error handling: dead camera stream, missing model file, invalid zone config — should not crash the whole service.

## Out of Scope (explicitly, for this MVP)
- Multi-camera dashboard UI (API only for now)
- User auth
- Cloud deployment / containerization
- Model fine-tuning or custom classes beyond person/vehicle
- Alerting integrations (SMS/email/webhook) — just log the event for now

## Ask
Please scaffold this project step by step: start with `capture.py` + a standalone test script that proves RTSP frames are being read at the target FPS, then add detection, then zone logic, then wrap it all in the FastAPI service. Explain any design trade-offs you make along the way (e.g., threading model, how you're handling frame buffering/backpressure, and whether local `ultralytics` vs. Ultralytics Platform makes more sense for this MVP).

## Implementation Clarifications

### Recommended module layout
Keep the repository small and explicit:

```text
app/
  main.py          # FastAPI application and lifecycle
  config.py        # YAML loading and validation
  capture.py       # Per-camera capture workers
  detector.py      # YOLO model loading and inference
  tracking.py      # Lightweight object identity across frames
  zones.py         # Polygon membership and entry transitions
  events.py        # Event persistence and filtering
  schemas.py       # Pydantic request/response models
scripts/
  test_capture.py
  test_detection.py
config.example.yaml
requirements.txt
README.md
tests/
```

The implementation may use a different layout, but capture, inference, tracking, zone logic, persistence, and HTTP concerns must remain separately testable.

### Tracking requirement
Zone-entry detection requires a stable object identity; raw detections do not have identity between frames. For the MVP, implement either:

- Ultralytics tracking with ByteTrack, or
- a documented lightweight IoU-based tracker.

Each track should have a temporary `track_id`, a configurable maximum age, and per-camera state. If tracking is unavailable, the system must fail clearly rather than generating an event on every frame.

Use the bottom-center of the bounding box as the default zone test point because it better represents where a person or vehicle is located on the ground. Make this configurable as `centroid` or `bottom_center`.

### Capture and backpressure behavior

- Use a bounded, size-one latest-frame buffer per camera.
- A capture worker must replace stale frames instead of blocking when inference is slower than capture.
- The inference loop must report capture FPS and inference FPS separately.
- Reconnect attempts must use bounded exponential backoff and must not terminate the application.
- Shutdown must signal workers and release `VideoCapture` handles cleanly.

### Configuration validation

Validate configuration at startup and provide actionable errors for missing fields, duplicate camera IDs, malformed RTSP URLs, invalid FPS values, unsupported classes, and polygons with fewer than three points. Invalid configuration should prevent startup with a readable message; runtime camera failures should not.

Include this minimum example:

```yaml
model: yolov8n.pt
device: auto                 # auto, cpu, or cuda:0
confidence: 0.5
target_fps: 8
zone_point: bottom_center
cameras:
  - id: entrance
    url: rtsp://user:password@camera/stream
    zones:
      - id: restricted-area
        polygon: [[100, 100], [500, 100], [500, 400], [100, 400]]
```

Secrets must not be logged. Support environment-variable substitution for camera URLs, for example `${ENTRANCE_RTSP_URL}`.

### API contract

Document request and response examples in the README and expose accurate OpenAPI schemas. At minimum:

- `GET /health` returns process health and model-load state.
- `GET /status` returns camera state, capture FPS, inference FPS, last frame time, and last error.
- `GET /events` supports `limit`, `offset` (or cursor), `camera_id`, `zone_id`, `object_class`, `from`, and `to`.
- `GET /cameras/{camera_id}/snapshot` returns `image/jpeg` and a useful `404` when no frame exists.
- `GET /zones` and `POST /zones` support camera and zone identifiers consistently; reject duplicate IDs.
- `DELETE /zones/{camera_id}/{zone_id}` removes a zone and its associated in-memory tracking state.

Use UTC ISO-8601 timestamps in API responses and SQLite records. Return consistent JSON error bodies for validation and not-found errors. Keep event deduplication behavior explicit: one event is emitted when a track changes from outside to inside a zone, and a new event may be emitted only after the track has left and re-entered (or expired).

### Persistence and retention

Use SQLite by default so events survive a process restart. Create the database schema automatically, add indexes for timestamp/camera/zone filters, and store bounding boxes as JSON. Add a configurable retention setting and a small cleanup command or startup cleanup hook; do not allow unbounded event growth.

### Testing and acceptance criteria

The project is complete when:

1. `python scripts/test_capture.py --source <rtsp-or-video-path> --seconds 20` reads frames, reports actual FPS, and exits nonzero with a useful message when the source cannot be opened.
2. A local video file can be used wherever an RTSP URL is expected, making the MVP testable without a camera.
3. Unit tests cover polygon boundaries, invalid polygons, entry versus continued presence, track expiry, event filtering, and configuration validation.
4. An integration test starts the API with a video-file source and verifies `/health`, `/status`, `/events`, and `/snapshot`.
5. The service continues running when a camera disconnects and exposes the disconnected state through `/status`.
6. An annotated snapshot visibly includes bounding boxes, class/confidence labels, zone outlines, and track IDs.
7. README instructions work on a clean Python 3.11 environment and explain model download, CPU performance expectations, video-file testing, RTSP troubleshooting, and how to stop the service.

### Privacy and operational safeguards

This MVP must not implement face recognition, identity inference, audio recording, or automatic decisions about individuals. Do not persist raw video by default; retain only event metadata and optional snapshots when explicitly configured. Add a README note that camera feeds and credentials must be handled according to applicable privacy, workplace, and local surveillance laws.
