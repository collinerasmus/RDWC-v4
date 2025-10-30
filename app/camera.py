import time
import threading
from typing import Generator

MODE = "unavailable"
_camera_lock = threading.Lock()

# Try picamera2 first
try:
    from picamera2 import Picamera2  # type: ignore
    import cv2  # type: ignore

    def _picam_frames(fps: int = 8, quality: int = 70):
        picam = Picamera2()
        config = picam.create_preview_configuration()
        picam.configure(config)
        picam.start()
        frame_interval = max(0.01, 1.0 / max(1, fps))
        try:
            while True:
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
        # No camera provider available; mark unavailable and provide a no-op generator
        def _noop_frames(fps: int = 5, quality: int = 70):
            # Intentionally yields nothing to signal clients there are no frames.
            while False:
                yield b""

        MODE = "unavailable"
        FRAMES_FN = _noop_frames


def get_status() -> dict:
    return {"mode": MODE, "available": MODE in ("picamera2", "opencv"), "note": "camera drivers unavailable"}


def frames(fps: int = 8, quality: int = 70) -> Generator[bytes, None, None]:
    """Yield JPEG frames according to selected provider (or nothing if unavailable)."""
    yield from FRAMES_FN(fps=fps, quality=quality)
