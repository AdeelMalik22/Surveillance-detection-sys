import argparse, time
from app.capture import CaptureWorker
parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--seconds", type=float, default=20); args = parser.parse_args()
worker = CaptureWorker("test", args.source, 8); worker.start(); time.sleep(args.seconds); worker.stop(); print(worker.status)
if worker.status.last_frame_at is None: raise SystemExit("No frames received")
