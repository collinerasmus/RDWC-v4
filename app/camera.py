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
    _cap = None
    _Image = None
    _Picamera2 = None
    _cv2 = None
    _lock = threading.Lock()

    @classmethod
    def _import_drivers(cls) -> bool:
        """Import Pillow, Picamera2 (preferred), and OpenCV (fallback)."""
        # Ensure system dist-packages are on sys.path for apt-installed modules (venv isolation fix)
        try:
            import sys
            for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"):
                if p not in sys.path:
                    sys.path.append(p)
        except Exception:
            pass

        # Pillow is required for JPEG encoding
        try:
            from PIL import Image  # type: ignore
            cls._Image = Image
        except Exception as e:
            cls.last_error = f"import_failed_pillow: {e}"
            return False

        # Picamera2 (try normal, now that sys.path is augmented)
        cls._Picamera2 = None
        try:
            from picamera2 import Picamera2  # type: ignore
            cls._Picamera2 = Picamera2
        except Exception:
            cls._Picamera2 = None

        # OpenCV (optional fallback)
        cls._cv2 = None
        try:
            import cv2  # type: ignore
            cls._cv2 = cv2
        except Exception:
            cls._cv2 = None

        if cls._Picamera2 is None and cls._cv2 is None:
            cls.last_error = "import_failed: no camera drivers (picamera2/opencv)"
            return False
        return True

    @classmethod
    def init(cls):
        if cls.available:
            return
        if not cls._import_drivers():
            cls.available = False
            cls.mode = "unavailable"
            return
        # Try Picamera2 first if available
        if cls._Picamera2 is not None:
            try:
                picam = cls._Picamera2()
                # For USB webcams via libcamera, try different format/size combos
                # YUYV, MJPEG are common for USB cams; RGB888 often fails
                configs_to_try = [
                    {"size": (1280, 720), "format": "YUYV"},
                    {"size": (1280, 720), "format": "MJPEG"},
                    {"size": (1024, 768), "format": "YUYV"},
                    {"size": (800, 600), "format": "YUYV"},
                    {"size": (640, 480), "format": "YUYV"},
                ]
                configured = False
                for config_params in configs_to_try:
                    try:
                        cfg = picam.create_video_configuration(
                            main=config_params,
                            buffer_count=4
                        )
                        picam.configure(cfg)
                        configured = True
                        print(f"[Camera] Configured with {config_params}")
                        break
                    except Exception:
                        continue
                if not configured:
                    raise Exception("No compatible camera configuration found")
                picam.start()
                # Allow camera to warm up and stabilize
                time.sleep(0.5)
                cls._picam = picam
                cls._cap = None
                cls.available = True
                cls.mode = "picamera2"
                cls.last_error = None
                return
            except Exception as e:
                cls.available = False
                cls.mode = "unavailable"
                cls.last_error = f"start_failed_picamera2: {e}"

        # Fallback to OpenCV (USB webcams)
        if cls._cv2 is not None:
            try:
                # Prefer V4L2 backend when available
                cap = None
                try:
                    cap = cls._cv2.VideoCapture(0, cls._cv2.CAP_V4L2)
                except Exception:
                    cap = cls._cv2.VideoCapture(0)
                if cap is not None and cap.isOpened():
                    # Try to set higher resolution for wider field of view
                    cap.set(3, 1280)  # WIDTH
                    cap.set(4, 720)   # HEIGHT
                    cls._cap = cap
                    cls._picam = None
                    cls.available = True
                    cls.mode = "opencv"
                    cls.last_error = None
                    return
                else:
                    cls.last_error = "start_failed_opencv: camera not opened"
            except Exception as e:
                cls.last_error = f"start_failed_opencv: {e}"

        # Nothing worked
        cls.available = False
        cls.mode = "unavailable"

    @classmethod
    def shutdown(cls):
        with cls._lock:
            try:
                if cls._picam:
                    cls._picam.stop()
                    cls._picam.close()
                if cls._cap is not None:
                    try:
                        cls._cap.release()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                cls._picam = None
                cls._cap = None
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
        """Multipart MJPEG stream with boundary=frame supporting picamera2 and opencv modes."""
        if not cls.available or cls._Image is None:
            yield (b"--frame\r\nContent-Type: application/json\r\n\r\n"
                   b'{"ok":false,"reason":"camera_unavailable"}\r\n')
            return

        interval = max(0.001, 1.0 / float(fps))
        frame_count = 0
        while True:
            try:
                if cls.mode == "picamera2" and cls._picam is not None:
                    # Capture from picamera2 (non-blocking with buffer)
                    frame = cls._picam.capture_array()
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    img = cls._Image.fromarray(frame)
                    # Log first frame info
                    if frame_count == 0:
                        print(f"[Camera] Frame shape: {frame.shape if hasattr(frame, 'shape') else 'N/A'}, PIL mode: {img.mode}")
                    # Convert to RGB if needed (Pillow may return LA, P, or other modes)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                elif cls.mode == "opencv" and cls._cap is not None and cls._cv2 is not None:
                    ret, frame = cls._cap.read()
                    if not ret:
                        time.sleep(0.2)
                        continue
                    # Convert BGR to RGB for Pillow
                    img = cls._Image.fromarray(frame[:, :, ::-1])
                else:
                    # No active camera
                    yield (b"--frame\r\nContent-Type: application/json\r\n\r\n"
                           b'{"ok":false,"reason":"no_active_camera"}\r\n')
                    time.sleep(0.5)
                    continue

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                jpg = buf.getvalue()
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                       + jpg + b"\r\n")
                frame_count += 1
                if frame_count == 1:
                    print(f"[Camera] First frame delivered (mode={cls.mode}, size={len(jpg)})")
                time.sleep(interval)
            except GeneratorExit:
                print(f"[Camera] Stream closed after {frame_count} frames")
                break
            except Exception as e:
                cls.last_error = f"stream_error: {e}"
                print(f"[Camera] Stream error: {e}")
                time.sleep(0.2)
