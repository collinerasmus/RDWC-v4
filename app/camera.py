import time
import threading
from typing import Generator, Tuple

MODE = "simulated"
_camera_lock = threading.Lock()

# Try picamera2 first
try:
    from picamera2 import Picamera2
    import numpy as np  # picamera2 often pairs with numpy
    import cv2

    def _picam_frames(fps: int = 8, quality: int = 70):
        picam = Picamera2()
        # Configure a simple preview configuration
        config = picam.create_preview_configuration()
        picam.configure(config)
        picam.start()
        frame_interval = max(0.01, 1.0 / max(1, fps))
        try:
            while True:
                # Capture frame as array
                arr = picam.capture_array()
                ok, enc = cv2.imencode('.jpg', arr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
                if not ok:
                    continue
                yield bytes(enc)
                time.sleep(frame_interval)
        finally:
            with _camera_lock:
                try:
                    picam.stop()
                except Exception:
                    pass

    MODE = "picamera2"
    FRAMES_FN = _picam_frames

except Exception:
    # Try OpenCV
    try:
        import cv2  # type: ignore

        def _cv2_frames(fps: int = 8, quality: int = 70):
            cap = cv2.VideoCapture(0)
            cap.set(cv2.CAP_PROP_FPS, fps)
            frame_interval = max(0.01, 1.0 / max(1, fps))
            try:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(0.1)
                        continue
                    ok, enc = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
                    if not ok:
                        continue
                    yield bytes(enc)
                    time.sleep(frame_interval)
            finally:
                with _camera_lock:
                    try:
                        cap.release()
                    except Exception:
                        pass

        MODE = "opencv"
        FRAMES_FN = _cv2_frames
    except Exception:
        import base64
        # 1x1 px black JPEG
        _JPEG_1x1 = base64.b64decode(
            b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhAQEA8QEA8QDw8PDw8QEA8PDw8PFREWFhURFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAJ8BPgMBIgACEQEDEQH/xAAbAAACAwEBAQAAAAAAAAAAAAAEBQIDBgABB//EADwQAAEDAgQDBgUEAwAAAAAAAAECAwQFEQAhBhIxQVFhByJxgZGh8BRCUrHB0WKyM2KS8RUzQ1Oy/8QAGQEAAwEBAQAAAAAAAAAAAAAAAAECAwQF/8QAJxEAAgIBAwMEAwAAAAAAAAAAAAECEQMhEjEEQVEiMmFxgZGhscH/2gAMAwEAAhEDEQA/AN+iiigAooooAKeR2V1bq9v5bXyHXr3e2gHq8Y2pDg7W2+gNfO4v1KhWgQxgS5b6s+qzVtWbJp2mJ7GZfJY2oF3b5k14yX8yYtmi1lZ4G9QqY4g3m+T0X6q1W0b5V2bR7i6tJkqzKpGY7j3A8fI2PAooopAkqS0k8YkYwABk+gq+uS1m1q1Z1w4H1NQH1r7mJNVqz2QYxH3WkY6jR9M3ZK8m2wBycZJ7c0f/Z"
        )

        def _sim_frames(fps: int = 5, quality: int = 70):
            frame_interval = max(0.01, 1.0 / max(1, fps))
            while True:
                yield _JPEG_1x1
                time.sleep(frame_interval)

        MODE = "simulated"
        FRAMES_FN = _sim_frames


def get_status() -> dict:
    return {"mode": MODE, "available": MODE in ("picamera2", "opencv"), "note": "simulated stream if drivers unavailable"}


def frames(fps: int = 8, quality: int = 70) -> Generator[bytes, None, None]:
    """Yield JPEG frames according to selected provider."""
    yield from FRAMES_FN(fps=fps, quality=quality)
