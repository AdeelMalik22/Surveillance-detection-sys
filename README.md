# AI Surveillance MVP

FastAPI MVP for RTSP or local-video capture, YOLO person/vehicle detection, polygon zones, and event storage.

```bash
cp config.example.yaml config.yaml
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs`. A local `.mp4` path can be used as a camera URL. Test capture with `python scripts/test_capture.py --source sample.mp4 --seconds 20`, or detection with `python scripts/test_detection.py --source sample.mp4 --seconds 20 --output annotated.jpg`. Detection is currently a standalone pipeline; tracking and zone-event integration follow next. Do not log RTSP credentials or persist raw video by default, and follow applicable surveillance and privacy laws.

Visit `http://127.0.0.1:8000/ui` to upload a video. The browser displays the backend's MJPEG stream with green boxes, class names, confidence, and temporary track IDs. This UI uploads video rather than images because real-time playback and tracking require a frame sequence.
