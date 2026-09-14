# AI Surveillance MVP

FastAPI MVP for RTSP or local-video capture, polygon zones, and event storage. YOLO is kept optional during the initial capture/API setup because its PyTorch dependency is large; install `ultralytics>=8.3` when enabling inference.

```bash
cp config.example.yaml config.yaml
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs`. A local `.mp4` path can be used as a camera URL. Test capture with `python scripts/test_capture.py --source sample.mp4 --seconds 20`. The API provides health, status, event filtering, JPEG snapshots, and zone CRUD. YOLO inference/tracking is the next integration layer; capture and zone logic are already independent. Do not log RTSP credentials or persist raw video by default, and follow applicable surveillance and privacy laws.
