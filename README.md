# AI Surveillance MVP

FastAPI MVP for RTSP or local-video capture, YOLO person/vehicle detection, polygon zones, and event storage.

Use a stable Python 3.11 release for PyTorch. The detector contains a small compatibility fallback for older 3.11 release-candidate environments, but recreating `.venv` with stable Python is preferred. Crowded or distant scenes use a lower confidence threshold (`0.3`) and larger inference size (`960`) to improve small-person recall; the live browser stream intentionally uses `640` and detects every fifth frame for better CPU responsiveness.

New person and vehicle tracks are recorded as events. Each event also attempts to save an MP4 clip containing approximately three seconds before and five seconds after detection. Clips are available from `/api/events/{session_id}/{event_id}/clip` and through the event links in the UI.

```bash
cp config.example.yaml config.yaml
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs`. A local `.mp4` path can be used as a camera URL. Test capture with `python scripts/test_capture.py --source sample.mp4 --seconds 20`, or detection with `python scripts/test_detection.py --source sample.mp4 --seconds 20 --output annotated.jpg`. Detection is currently a standalone pipeline; tracking and zone-event integration follow next. Do not log RTSP credentials or persist raw video by default, and follow applicable surveillance and privacy laws.

Visit `http://127.0.0.1:8000/ui` to upload a video. The browser displays the backend's MJPEG stream with green boxes, class names, confidence, and temporary track IDs. This UI uploads video rather than images because real-time playback and tracking require a frame sequence.
