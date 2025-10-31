"""
Camera module for RDWC v4 - Picamera2 MJPEG streaming with diagnostics
No OpenCV dependency - uses Pillow (PIL) for JPEG encoding
"""
import io
import time
import threading
from typing import Optional, Dict, Generator


class CameraManager:
    available: bool = False
    mode: str = "unavailable"
    last_error: Optional[str] = None
    _picam = None
    _Image = None
    _Picamera2 = None
    _lock = threading.Lock()

    @classmethod
    def _import_drivers(cls) -> bool:
        """Import Picamera2 and PIL; attempt system dist-packages path on failure."""
        try:
            from picamera2 import Picamera2  # type: ignore
            from PIL import Image  # type: ignore
            cls._Picamera2 = Picamera2
            cls._Image = Image
            return True
        except Exception:
            # Try system paths if running inside a venv
            try:
                import sys
                for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"):
                    if p not in sys.path:
                        sys.path.append(p)
                from picamera2 import Picamera2  # type: ignore
                from PIL import Image  # type: ignore
                cls._Picamera2 = Picamera2
                cls._Image = Image
                return True
            except Exception as e2:
                cls.last_error = f"import_failed: {e2}"
                return False

    @classmethod
    def init(cls):
        if cls.available:
            return
        if not cls._import_drivers():
            cls.available = False
            cls.mode = "unavailable"
            return
        try:
            if cls._Picamera2 is None or cls._Image is None:
                cls.available = False
                cls.mode = "unavailable"
                cls.last_error = "drivers_not_loaded"
                return
            picam = cls._Picamera2()
            cfg = picam.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
            picam.configure(cfg)
            picam.start()
            # Warm-up
            time.sleep(0.3)
            cls._picam = picam
            cls.available = True
            cls.mode = "picamera2"
            cls.last_error = None
        except Exception as e:
            cls.available = False
            cls.mode = "unavailable"
            cls.last_error = f"start_failed: {e}"

    @classmethod
    def shutdown(cls):
        with cls._lock:
            try:
                if cls._picam:
                    cls._picam.stop()
                    cls._picam.close()
            except Exception:
                pass
            finally:
                cls._picam = None
                cls.available = False
                cls.mode = "unavailable"

    @classmethod
    def status(cls) -> Dict:
        return {
            "available": cls.available,
            "mode": cls.mode,
            "last_error": cls.last_error,
            "note": cls.last_error or "Camera ready",
        }

    @classmethod
    def mjpeg_generator(cls, fps: int = 5) -> Generator[bytes, None, None]:
        """Multipart MJPEG stream with boundary=frame"""
        if not cls.available or not cls._picam or not cls._Image:
            yield (b"--frame\r\nContent-Type: application/json\r\n\r\n"
                   b'{"ok":false,"reason":"camera_unavailable"}\r\n')
            return
        interval = max(0.001, 1.0 / float(fps))
        while True:
            try:
                frame = cls._picam.capture_array()
                buf = io.BytesIO()
                cls._Image.fromarray(frame).save(buf, format="JPEG", quality=70)
                jpg = buf.getvalue()
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                       + jpg + b"\r\n")
                time.sleep(interval)
            except GeneratorExit:
                break
            except Exception as e:
                cls.last_error = f"stream_error: {e}"
                time.sleep(0.2)
