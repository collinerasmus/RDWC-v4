"""Camera manager with live stream and timelapse session support."""
import io
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class CameraManager:
    available: bool = False
    mode: str = "unavailable"
    last_error: Optional[str] = None
    _cap = None
    _Image = None
    _cv2 = None
    _lock = threading.Lock()
    _camera_index = None
    _last_init_attempt = 0.0
    _init_retry_s = 5.0
    _default_max_frames = int(os.environ.get("CAM_TIMELAPSE_DEFAULT_MAX_FRAMES", "12000"))
    _max_total_bytes = int(os.environ.get("CAM_TIMELAPSE_MAX_TOTAL_MB", "4096")) * 1024 * 1024

    _store_dir = Path(__file__).resolve().parent.parent / "data" / "timelapse"
    _settings_path = _store_dir / "settings.json"
    _tl_lock = threading.Lock()
    _tl_stop = threading.Event()
    _tl_thread: Optional[threading.Thread] = None
    _tl_state: Dict[str, Any] = {
        "running": False,
        "interval_s": 300,
        "quality": 80,
        "max_frames": _default_max_frames,
        "frame_count": 0,
        "label": "grow",
        "session_id": None,
        "session_dir": None,
        "last_capture_ts": None,
        "last_frame": None,
        "next_capture_ts": None,
        "last_error": None,
        "started_at": None,
        "stopped_reason": None,
    }

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
        if cls.available and cls._cap is not None:
            return
        if not cls._import_drivers():
            cls.available = False
            cls.mode = "unavailable"
            return

        cls._open_camera()

        cls._load_settings()

    @classmethod
    def _candidate_indexes(cls):
        raw = os.environ.get("CAM_INDEX", "0,1")
        out = []
        for part in str(raw).split(","):
            p = part.strip()
            if not p:
                continue
            try:
                out.append(int(p))
            except Exception:
                continue
        if not out:
            out = [0, 1]
        return out

    @classmethod
    def _open_camera(cls):
        if cls._cv2 is None:
            cls.available = False
            cls.mode = "unavailable"
            cls.last_error = cls.last_error or "opencv_not_loaded"
            return

        # Release stale handle before retrying open
        with cls._lock:
            try:
                if cls._cap is not None:
                    cls._cap.release()
            except Exception:
                pass
            cls._cap = None

        errors = []
        for idx in cls._candidate_indexes():
            cap = None
            try:
                cap = cls._cv2.VideoCapture(idx, cls._cv2.CAP_V4L2) if hasattr(cls._cv2, "CAP_V4L2") else cls._cv2.VideoCapture(idx)
                if cap is not None and cap.isOpened():
                    cap.set(3, 1280)
                    cap.set(4, 720)
                    with cls._lock:
                        cls._cap = cap
                    cls.available = True
                    cls.mode = "opencv"
                    cls.last_error = None
                    cls._camera_index = idx
                    return
                errors.append(f"idx{idx}:not_open")
            except Exception as e:
                errors.append(f"idx{idx}:{e}")
            finally:
                try:
                    if cap is not None and (cls._cap is None or cap is not cls._cap):
                        cap.release()
                except Exception:
                    pass

        cls.available = False
        cls.mode = "unavailable"
        cls._camera_index = None
        cls.last_error = "start_failed: " + ";".join(errors or ["camera_not_opened"])

    @classmethod
    def _ensure_store_dir(cls):
        cls._store_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _load_settings(cls):
        cls._ensure_store_dir()
        if not cls._settings_path.exists():
            return
        try:
            data = json.loads(cls._settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cls._tl_state["interval_s"] = int(data.get("interval_s", cls._tl_state["interval_s"]))
                cls._tl_state["quality"] = int(data.get("quality", cls._tl_state["quality"]))
                cls._tl_state["max_frames"] = int(data.get("max_frames", cls._tl_state["max_frames"]))
                cls._tl_state["label"] = str(data.get("label", cls._tl_state["label"]))
                if cls._tl_state["max_frames"] <= 0:
                    cls._tl_state["max_frames"] = cls._default_max_frames
        except Exception:
            pass

    @classmethod
    def _save_settings(cls):
        cls._ensure_store_dir()
        payload = {
            "interval_s": cls._tl_state["interval_s"],
            "quality": cls._tl_state["quality"],
            "max_frames": cls._tl_state["max_frames"],
            "label": cls._tl_state["label"],
        }
        try:
            cls._settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def _is_open(cls) -> bool:
        try:
            return bool(cls.available and cls._cap is not None and cls._cap.isOpened())
        except Exception:
            return False

    @classmethod
    def ensure_ready(cls) -> bool:
        if cls._is_open():
            return True
        now = time.time()
        if (now - cls._last_init_attempt) < cls._init_retry_s:
            return False
        cls._last_init_attempt = now
        cls.init()
        return cls._is_open()

    @classmethod
    def shutdown(cls):
        cls.stop_timelapse(reason="shutdown")
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
        if not cls._is_open():
            cls.ensure_ready()
        return {
            "available": cls._is_open(),
            "mode": cls.mode,
            "camera_index": cls._camera_index,
            "last_error": cls.last_error,
            "note": cls.last_error or ("Camera ready" if cls._is_open() else "Unavailable"),
        }

    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _sanitize_label(cls, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "grow")).strip("-")
        return cleaned[:48] or "grow"

    @classmethod
    def _validate_timelapse_settings(cls, settings: Optional[dict] = None) -> Dict[str, Any]:
        settings = settings or {}
        interval_s = int(settings.get("interval_s", cls._tl_state["interval_s"]))
        quality = int(settings.get("quality", cls._tl_state["quality"]))
        max_frames = int(settings.get("max_frames", cls._tl_state["max_frames"]))
        label = cls._sanitize_label(str(settings.get("label", cls._tl_state["label"])))

        interval_s = max(10, min(86400, interval_s))
        quality = max(30, min(95, quality))
        if max_frames <= 0:
            max_frames = cls._default_max_frames
        max_frames = max(100, min(100000, max_frames))

        return {
            "interval_s": interval_s,
            "quality": quality,
            "max_frames": max_frames,
            "label": label,
        }

    @classmethod
    def _capture_jpeg(cls, quality: int) -> Optional[bytes]:
        if not cls._is_open() and not cls.ensure_ready():
            return None
        if cls._cv2 is None or cls._cap is None:
            return None
        with cls._lock:
            try:
                ret, frame = cls._cap.read()
                if not ret or frame is None:
                    return None
                ok, jpeg = cls._cv2.imencode(".jpg", frame, [int(cls._cv2.IMWRITE_JPEG_QUALITY), int(quality)])
                if not ok:
                    return None
                return jpeg.tobytes()
            except Exception as e:
                cls.last_error = f"capture_error: {e}"
                return None

    @classmethod
    def _create_session_dir(cls, label: str) -> Path:
        cls._ensure_store_dir()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        sid = f"{stamp}_{label}"
        path = cls._store_dir / sid
        path.mkdir(parents=True, exist_ok=True)
        meta = {
            "session_id": sid,
            "label": label,
            "started_at": cls._now_iso(),
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    @classmethod
    def _session_size_bytes(cls, p: Path) -> int:
        total = 0
        try:
            for e in p.iterdir():
                if e.is_file():
                    total += e.stat().st_size
        except Exception:
            return total
        return total

    @classmethod
    def _prune_sessions(cls, keep_session_id: Optional[str] = None):
        if cls._max_total_bytes <= 0:
            return
        try:
            dirs = [p for p in cls._store_dir.iterdir() if p.is_dir()]
        except Exception:
            return

        sessions = []
        total = 0
        for p in dirs:
            size = cls._session_size_bytes(p)
            total += size
            sessions.append((p, size))

        if total <= cls._max_total_bytes:
            return

        sessions.sort(key=lambda item: item[0].name)
        for p, size in sessions:
            if total <= cls._max_total_bytes:
                break
            if keep_session_id and p.name == keep_session_id:
                continue
            try:
                for e in p.iterdir():
                    if e.is_file():
                        e.unlink(missing_ok=True)
                p.rmdir()
                total -= size
            except Exception:
                continue

    @classmethod
    def _write_frame(cls, session_dir: Path, frame_no: int, quality: int) -> Optional[str]:
        jpeg = cls._capture_jpeg(quality=quality)
        if jpeg is None:
            return None
        frame_name = f"frame_{frame_no:06d}.jpg"
        frame_path = session_dir / frame_name
        frame_path.write_bytes(jpeg)
        return str(frame_path)

    @classmethod
    def _timelapse_loop(cls):
        while not cls._tl_stop.is_set():
            with cls._tl_lock:
                if not cls._tl_state["running"]:
                    break
                session_dir = cls._tl_state.get("session_dir")
                frame_no = int(cls._tl_state.get("frame_count", 0)) + 1
                interval_s = int(cls._tl_state.get("interval_s", 300))
                quality = int(cls._tl_state.get("quality", 80))
                max_frames = int(cls._tl_state.get("max_frames", 0))

            if not session_dir:
                cls._tl_state["last_error"] = "missing_session_dir"
                time.sleep(1)
                continue

            out = cls._write_frame(Path(session_dir), frame_no=frame_no, quality=quality)
            now = time.time()

            with cls._tl_lock:
                if out:
                    cls._tl_state["frame_count"] = frame_no
                    cls._tl_state["last_capture_ts"] = now
                    cls._tl_state["last_frame"] = out
                    cls._tl_state["last_error"] = None
                else:
                    cls._tl_state["last_error"] = "capture_failed"

                if max_frames > 0 and int(cls._tl_state["frame_count"]) >= max_frames:
                    cls._tl_state["stopped_reason"] = "max_frames"
                    cls._tl_state["running"] = False
                    cls._tl_state["next_capture_ts"] = None
                    break

                cls._tl_state["next_capture_ts"] = now + interval_s

            waited = cls._tl_stop.wait(timeout=max(1, interval_s))
            if waited:
                break

        with cls._tl_lock:
            cls._tl_state["running"] = False
            cls._tl_state["next_capture_ts"] = None

    @classmethod
    def timelapse_status(cls) -> Dict[str, Any]:
        with cls._tl_lock:
            st = dict(cls._tl_state)
        next_in = None
        if st.get("running") and st.get("next_capture_ts"):
            next_in = max(0, int(float(st["next_capture_ts"]) - time.time()))
        st["next_capture_in_s"] = next_in
        st["available"] = cls._is_open()
        return st

    @classmethod
    def start_timelapse(cls, settings: Optional[dict] = None) -> Dict[str, Any]:
        if not cls.ensure_ready():
            with cls._tl_lock:
                cls._tl_state["last_error"] = "camera_unavailable"
            return {"ok": False, "error": "camera_unavailable", "status": cls.timelapse_status()}

        valid = cls._validate_timelapse_settings(settings)
        with cls._tl_lock:
            if cls._tl_state["running"]:
                return {"ok": True, "already_running": True, "status": cls.timelapse_status()}

            session_dir = cls._create_session_dir(valid["label"])
            session_id = session_dir.name

            cls._tl_state.update(
                {
                    "running": True,
                    "interval_s": valid["interval_s"],
                    "quality": valid["quality"],
                    "max_frames": valid["max_frames"],
                    "label": valid["label"],
                    "session_id": session_id,
                    "session_dir": str(session_dir),
                    "frame_count": 0,
                    "last_capture_ts": None,
                    "last_frame": None,
                    "last_error": None,
                    "started_at": cls._now_iso(),
                    "stopped_reason": None,
                    "next_capture_ts": time.time(),
                }
            )
            cls._save_settings()
            cls._prune_sessions(keep_session_id=session_id)

            cls._tl_stop.clear()
            cls._tl_thread = threading.Thread(target=cls._timelapse_loop, name="camera_timelapse", daemon=True)
            cls._tl_thread.start()

        return {"ok": True, "status": cls.timelapse_status()}

    @classmethod
    def stop_timelapse(cls, reason: str = "manual") -> Dict[str, Any]:
        with cls._tl_lock:
            was_running = bool(cls._tl_state["running"])
            cls._tl_state["running"] = False
            cls._tl_state["stopped_reason"] = reason
            cls._tl_state["next_capture_ts"] = None

        cls._tl_stop.set()
        t = cls._tl_thread
        if t and t.is_alive():
            t.join(timeout=3)
        cls._tl_thread = None

        return {"ok": True, "was_running": was_running, "status": cls.timelapse_status()}

    @classmethod
    def capture_now(cls, quality: Optional[int] = None) -> Dict[str, Any]:
        if not cls.ensure_ready():
            with cls._tl_lock:
                cls._tl_state["last_error"] = "camera_unavailable"
            return {"ok": False, "error": "camera_unavailable", "status": cls.timelapse_status()}

        with cls._tl_lock:
            q = int(quality or cls._tl_state.get("quality", 80))
            q = max(30, min(95, q))
            running = bool(cls._tl_state.get("running"))
            session_dir = cls._tl_state.get("session_dir")
            frame_no = int(cls._tl_state.get("frame_count", 0)) + 1

        if not session_dir:
            session = cls._create_session_dir("manual")
            session_dir = str(session)

        out = cls._write_frame(Path(session_dir), frame_no=frame_no, quality=q)
        if out is None:
            return {"ok": False, "error": "capture_failed"}

        now = time.time()
        with cls._tl_lock:
            cls._tl_state["frame_count"] = frame_no
            cls._tl_state["last_capture_ts"] = now
            cls._tl_state["last_frame"] = out
            cls._tl_state["session_dir"] = session_dir
            if cls._tl_state.get("session_id") is None:
                cls._tl_state["session_id"] = Path(session_dir).name
                cls._tl_state["started_at"] = cls._now_iso()
            if not running:
                cls._tl_state["stopped_reason"] = "manual_capture"

        return {"ok": True, "path": out, "status": cls.timelapse_status()}

    @classmethod
    def list_sessions(cls, limit: int = 20):
        cls._ensure_store_dir()
        dirs = [p for p in cls._store_dir.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.name, reverse=True)
        out = []
        for p in dirs[: max(1, min(100, int(limit)) )]:
            frame_count = 0
            first = None
            last = None
            try:
                for f in p.glob("frame_*.jpg"):
                    name = f.name
                    frame_count += 1
                    if first is None or name < first:
                        first = name
                    if last is None or name > last:
                        last = name
            except Exception:
                pass
            out.append(
                {
                    "session_id": p.name,
                    "path": str(p),
                    "frames": frame_count,
                    "first_frame": first,
                    "last_frame": last,
                }
            )
        return out

    @classmethod
    def capture_single_frame(cls) -> Optional[bytes]:
        if not cls._is_open() and not cls.ensure_ready():
            return None
        if cls._Image is None or cls._cap is None:
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
        return cls._is_open()

    @classmethod
    def mjpeg_generator(cls, fps: int = 8):
        """Lightweight MJPEG streaming generator for /camera/stream endpoint.
        Uses OpenCV frame capture with configurable FPS throttling."""
        import time
        if not cls._is_open() and not cls.ensure_ready():
            yield b''
            return
        if cls._cap is None:
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
