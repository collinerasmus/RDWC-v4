"""
Camera module for RDWC v4 - Picamera2 MJPEG streaming with graceful fallback
No OpenCV dependency - uses PIL for JPEG encoding
"""
import io
import time
import threading
from typing import Generator, Dict, Any

MODE = "unavailable"
_camera_lock = threading.Lock()
_picam_instance = None

# Try to import Picamera2, with fallback to system site-packages on Raspberry Pi
PICAMERA2_AVAILABLE = False
Picamera2 = None
try:
    from picamera2 import Picamera2  # type: ignore
    PICAMERA2_AVAILABLE = True
except ImportError:
    # Attempt to include system dist-packages (apt-installed modules) in sys.path
    try:
        import sys
        sys_paths = [
            "/usr/lib/python3/dist-packages",
            "/usr/local/lib/python3/dist-packages",
        ]
        for p in sys_paths:
            if p not in sys.path:
                sys.path.append(p)
        from picamera2 import Picamera2  # type: ignore
        PICAMERA2_AVAILABLE = True
    except Exception:
        PICAMERA2_AVAILABLE = False
        Picamera2 = None

# PIL for JPEG encoding (lighter than OpenCV)
try:
    from PIL import Image  # type: ignore
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


def _init_camera():
    """Initialize camera on first use"""
    global _picam_instance, MODE
    
    if not PICAMERA2_AVAILABLE:
        MODE = "unavailable"
        return None
    
    if not PIL_AVAILABLE:
        MODE = "unavailable"
        return None
    
    with _camera_lock:
        if _picam_instance is not None:
            return _picam_instance
        
        try:
            picam = Picamera2()
            # Configure for MJPEG streaming: 640x480 @ RGB888, ~5-10 fps
            config = picam.create_video_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            picam.configure(config)
            picam.start()
            
            # Give camera a moment to warm up
            time.sleep(0.5)
            
            _picam_instance = picam
            MODE = "picamera2"
            return picam
            
        except Exception as e:
            print(f"Failed to initialize Picamera2: {e}")
            MODE = "unavailable"
            return None


def _picam_frames(fps: int = 5, quality: int = 70) -> Generator[bytes, None, None]:
    """Generate MJPEG frames using Picamera2 + PIL"""
    picam = _init_camera()
    if not picam:
        return
    
    frame_interval = 1.0 / max(1, fps)
    last_frame_time = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Rate limit
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.05)
                continue
            
            try:
                # Capture frame
                frame = picam.capture_array()
                
                # Convert to JPEG using PIL
                img = Image.fromarray(frame)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                jpeg_bytes = buf.getvalue()
                
                yield jpeg_bytes
                last_frame_time = current_time
                
            except Exception as e:
                # Skip this frame on error
                print(f"Camera frame capture error: {e}")
                time.sleep(0.1)
                continue
                
    except GeneratorExit:
        # Generator closed, cleanup handled by shutdown()
        pass


def _noop_frames(fps: int = 5, quality: int = 70) -> Generator[bytes, None, None]:
    """No-op generator when camera unavailable"""
    while False:
        yield b""


# Set the frame generator based on availability
if PICAMERA2_AVAILABLE and PIL_AVAILABLE:
    # Will initialize on first use
    FRAMES_FN = _picam_frames
else:
    MODE = "unavailable"
    FRAMES_FN = _noop_frames


def get_status() -> Dict[str, Any]:
    """Return camera status"""
    note = None
    if not PICAMERA2_AVAILABLE:
        note = "picamera2 not installed (add /usr/lib/python3/dist-packages or apt install python3-picamera2)"
    elif not PIL_AVAILABLE:
        note = "PIL/Pillow not installed"
    elif MODE == "unavailable":
        note = "camera not initialized or failed to start"
    
    return {
        "mode": MODE,
        "available": MODE == "picamera2",
        "note": note or "Camera ready"
    }


def frames(fps: int = 5, quality: int = 70) -> Generator[bytes, None, None]:
    """Yield JPEG frames according to selected provider (or nothing if unavailable)"""
    yield from FRAMES_FN(fps=fps, quality=quality)


def shutdown():
    """Clean shutdown of camera"""
    global _picam_instance
    with _camera_lock:
        if _picam_instance:
            try:
                _picam_instance.stop()
                _picam_instance.close()
            except Exception as e:
                print(f"Camera shutdown error: {e}")
            finally:
                _picam_instance = None
