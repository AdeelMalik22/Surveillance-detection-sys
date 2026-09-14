import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.capture import CaptureWorker
from app.detector import Detector
from app.pipeline import ProcessingPipeline

parser = argparse.ArgumentParser(description="Run YOLO detection on a video or RTSP source")
parser.add_argument("--source", required=True)
parser.add_argument("--model", default="yolov8n.pt")
parser.add_argument("--confidence", type=float, default=0.3)
parser.add_argument("--image-size", type=int, default=960)
parser.add_argument("--seconds", type=float, default=20)
parser.add_argument("--output", default="annotated.jpg")
args = parser.parse_args()

worker = CaptureWorker("detection-test", args.source, target_fps=8)
detector = Detector(args.model, args.confidence, image_size=args.image_size)
pipeline = ProcessingPipeline(worker, detector, target_fps=8)
worker.start()
pipeline.start()
started = time.monotonic()
latest = None
try:
    while time.monotonic() - started < args.seconds:
        latest = pipeline.latest_annotated()
        if latest is None:
            time.sleep(0.05)
            continue
        time.sleep(0.05)
finally:
    pipeline.stop()
    worker.stop()

if latest is None:
    raise SystemExit("No frames received")
cv2.imwrite(args.output, latest)
print(f"inference_fps={pipeline.inference_fps:.2f}; saved annotated frame to {args.output}")
