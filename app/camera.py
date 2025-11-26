"""Simplified camera module: snapshot-only OpenCV capture.
Streaming and Picamera2 modes removed for stability and reduced load."""
import io
import threading
from typing import Optional, Dict


class CameraManager:
    available: bool = False
    mode: str = "unavailable"
    last_error: Optional[str] = None
    _cap = None
    _Image = None
    _cv2 = None
    _lock = threading.Lock()

    @classmethod
    def _import_drivers(cls) -> bool:
        try:
            from PIL import Image  # type: ignore
            cls._Image = Image
        except Exception as e:
            cls.last_error = f"import_failed_pillow: {e}"
            return False
        try:
            import cv2  # type: ignore
            cls._cv2 = cv2
        except Exception as e:
            cls.last_error = f"import_failed_opencv: {e}"
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
        try:
            cap = cls._cv2.VideoCapture(0, cls._cv2.CAP_V4L2) if hasattr(cls._cv2, "CAP_V4L2") else cls._cv2.VideoCapture(0)
            if cap is not None and cap.isOpened():
                cap.set(3, 1280)
                cap.set(4, 720)
                cls._cap = cap
                cls.available = True
                cls.mode = "opencv"
                cls.last_error = None
            else:
                cls.last_error = "start_failed: camera not opened"
        except Exception as e:
            cls.last_error = f"start_failed: {e}"
            cls.available = False
            cls.mode = "unavailable"

    @classmethod
    def shutdown(cls):
        with cls._lock:
            try:
                if cls._cap is not None:
                    cls._cap.release()
            except Exception:
                pass
            finally:
                cls._cap = None
                cls.available = False
                cls.mode = "unavailable"

    @classmethod
    def status(cls) -> Dict:
        return {
            "available": cls.available,
            "mode": cls.mode,
            "last_error": cls.last_error,
            "note": cls.last_error or ("Camera ready" if cls.available else "Unavailable"),
        }

    @classmethod
    def capture_single_frame(cls) -> Optional[bytes]:
        if not cls.available or cls._Image is None or cls._cap is None:
            return None
        with cls._lock:
            try:
                ret, frame = cls._cap.read()
                if ret and frame is not None:
                    img = cls._Image.fromarray(frame[:, :, ::-1])  # BGR->RGB
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=70)
                    return buf.getvalue()
            except Exception as e:
                cls.last_error = f"snapshot_error: {e}"
        return None

    @classmethod
    def is_healthy(cls) -> bool:
        return bool(cls.available and cls._cap is not None and cls._cap.isOpened())

    @classmethod
    def mjpeg_generator(cls, fps: int = 8):
        """Lightweight MJPEG streaming generator for /camera/stream endpoint.
        Uses OpenCV frame capture with configurable FPS throttling."""
        import time
        if not cls.available or cls._cap is None:
            yield b''
            return
        
        frame_delay = 1.0 / fps if fps > 0 else 0.125
        boundary = b"frame"
        
        while True:
            if not cls.is_healthy():
                break
            
            with cls._lock:
                try:
                    ret, frame = cls._cap.read()
                    if not ret or frame is None:
                        time.sleep(frame_delay)
                        continue
                    
                    # Encode frame as JPEG
                    ret, jpeg = cls._cv2.imencode('.jpg', frame, [int(cls._cv2.IMWRITE_JPEG_QUALITY), 70])
                    if not ret:
                        time.sleep(frame_delay)
                        continue
                    
                    frame_bytes = jpeg.tobytes()
                    
                    # Yield multipart frame
                    yield (b'--' + boundary + b'\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                           b'\r\n' + frame_bytes + b'\r\n')
                    
                except Exception as e:
                    cls.last_error = f"stream_error: {e}"
                    break
            
            time.sleep(frame_delay)
