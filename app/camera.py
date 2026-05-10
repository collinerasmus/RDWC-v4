"""Camera manager with live stream and timelapse session support."""
import json
import os
import re
import threading
import time
import math
from contextlib import suppress
from datetime import datetime, timezone, timedelta
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
    _default_interval_s = int(os.environ.get("CAM_TIMELAPSE_DEFAULT_INTERVAL_S", "600"))
    _default_quality = int(os.environ.get("CAM_TIMELAPSE_DEFAULT_QUALITY", "88"))
    _default_max_frames = int(os.environ.get("CAM_TIMELAPSE_DEFAULT_MAX_FRAMES", str(max(1000, int((56 * 86400) / max(10, _default_interval_s))))))
    _max_total_bytes = int(os.environ.get("CAM_TIMELAPSE_MAX_TOTAL_MB", "4096")) * 1024 * 1024
    _default_stream_fps = int(os.environ.get("CAM_STREAM_FPS", "10"))
    _default_stream_quality = int(os.environ.get("CAM_STREAM_QUALITY", "85"))
    _default_snapshot_quality = int(os.environ.get("CAM_SNAPSHOT_QUALITY", "90"))
    _default_width = int(os.environ.get("CAM_WIDTH", "1920"))
    _default_height = int(os.environ.get("CAM_HEIGHT", "1080"))
    _default_lights_on_only = os.environ.get("CAM_TIMELAPSE_LIGHTS_ON_ONLY", "true").strip().lower() in ("1", "true", "yes", "on")
    _auto_exposure_tune = os.environ.get("CAM_EXPOSURE_AUTO_TUNE", "true").strip().lower() in ("1", "true", "yes", "on")
    _exposure_target_luma = float(os.environ.get("CAM_EXPOSURE_TARGET_LUMA", "140"))
    _exposure_alpha_min = float(os.environ.get("CAM_EXPOSURE_ALPHA_MIN", "0.6"))
    _exposure_alpha_max = float(os.environ.get("CAM_EXPOSURE_ALPHA_MAX", "1.25"))

    _store_dir = Path(__file__).resolve().parent.parent / "data" / "timelapse"
    _settings_path = _store_dir / "settings.json"
    _tl_lock = threading.Lock()
    _tl_stop = threading.Event()
    _tl_thread: Optional[threading.Thread] = None
    _tl_state: Dict[str, Any] = {
        "running": False,
        "interval_s": _default_interval_s,
        "quality": _default_quality,
        "max_frames": _default_max_frames,
        "lights_on_only": _default_lights_on_only,
        "frame_count": 0,
        "skipped_captures": 0,
        "label": "grow",
        "session_id": None,
        "session_dir": None,
        "last_capture_ts": None,
        "last_frame": None,
        "last_skip_reason": None,
        "next_capture_ts": None,
        "last_error": None,
        "started_at": None,
        "stopped_reason": None,
    }

    @classmethod
    def _to_bool(cls, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "on")

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
                    # Tune capture path for sharper, lower-latency feed on Pi cameras.
                    with suppress(Exception):
                        cap.set(cls._cv2.CAP_PROP_FOURCC, cls._cv2.VideoWriter_fourcc(*"MJPG"))
                    with suppress(Exception):
                        cap.set(cls._cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(3, max(640, cls._default_width))
                    cap.set(4, max(480, cls._default_height))
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
                cls._tl_state["lights_on_only"] = cls._to_bool(data.get("lights_on_only", cls._tl_state.get("lights_on_only", cls._default_lights_on_only)), default=cls._default_lights_on_only)
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
            "lights_on_only": bool(cls._tl_state.get("lights_on_only", cls._default_lights_on_only)),
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
        lights_on_only = cls._to_bool(settings.get("lights_on_only", cls._tl_state.get("lights_on_only", cls._default_lights_on_only)), default=cls._default_lights_on_only)
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
            "lights_on_only": lights_on_only,
            "label": label,
        }

    @classmethod
    def _capture_allowed_now(cls, lights_on_only: bool) -> Dict[str, Any]:
        if not lights_on_only:
            return {"allowed": True, "reason": "always"}
        try:
            from app.settings import get_todays_lights_window

            now = datetime.now().astimezone()
            on_dt, off_dt = get_todays_lights_window()
            if on_dt.tzinfo is None:
                on_dt = on_dt.replace(tzinfo=now.tzinfo)
            if off_dt.tzinfo is None:
                off_dt = off_dt.replace(tzinfo=now.tzinfo)

            if off_dt <= on_dt:
                off_dt = off_dt + timedelta(days=1)
            in_window = on_dt <= now < off_dt
            return {
                "allowed": bool(in_window),
                "reason": "lights_on" if in_window else "lights_off",
                "window": {
                    "on": on_dt.isoformat(),
                    "off": off_dt.isoformat(),
                },
            }
        except Exception:
            # Fail-open so capture continues if schedule lookup fails.
            return {"allowed": True, "reason": "schedule_unknown"}

    @classmethod
    def _estimate_bytes_per_frame(cls, quality: int) -> int:
        # Prefer measured frame sizes from recent sessions; otherwise use a conservative heuristic.
        measured = []
        try:
            for s in cls.list_sessions(limit=5):
                p = Path(s.get("path", ""))
                if not p.exists() or not p.is_dir():
                    continue
                frame_sizes = [f.stat().st_size for f in sorted(p.glob("frame_*.jpg"))[:20] if f.is_file()]
                if frame_sizes:
                    measured.append(sum(frame_sizes) / float(len(frame_sizes)))
        except Exception:
            measured = []

        if measured:
            return int(sum(measured) / float(len(measured)))

        megapixels = (max(640, cls._default_width) * max(480, cls._default_height)) / 1_000_000.0
        q_factor = max(0.5, min(1.5, quality / 85.0))
        # Rough JPEG size estimate for foliage-rich scenes at 1080p range.
        return int(max(60_000, 120_000 * megapixels * q_factor))

    @classmethod
    def _auto_tune_exposure(cls, frame):
        if not cls._auto_exposure_tune or cls._cv2 is None or frame is None:
            return frame
        try:
            gray = cls._cv2.cvtColor(frame, cls._cv2.COLOR_BGR2GRAY)
            mean_luma = float(gray.mean())
            if mean_luma <= 1:
                return frame
            alpha = cls._exposure_target_luma / mean_luma
            alpha = max(cls._exposure_alpha_min, min(cls._exposure_alpha_max, alpha))
            if abs(alpha - 1.0) < 0.03:
                return frame
            return cls._cv2.convertScaleAbs(frame, alpha=alpha, beta=0)
        except Exception:
            return frame

    @classmethod
    def recommended_timelapse(cls, grow_days: int = 56, output_fps: int = 24) -> Dict[str, Any]:
        grow_days = max(14, min(120, int(grow_days)))
        output_fps = max(12, min(60, int(output_fps)))
        interval_s = max(120, min(1800, cls._default_interval_s))
        frames = int(math.ceil((grow_days * 86400) / float(interval_s)))
        max_frames = min(100000, max(frames, cls._default_max_frames))
        est_seconds = round(frames / float(output_fps), 1)
        est_minutes = round(est_seconds / 60.0, 1)
        est_bytes_per_frame = cls._estimate_bytes_per_frame(quality=max(80, min(95, cls._default_quality)))
        est_storage_mb = round((frames * est_bytes_per_frame) / (1024.0 * 1024.0), 1)
        return {
            "grow_days": grow_days,
            "interval_s": interval_s,
            "quality": max(80, min(95, cls._default_quality)),
            "max_frames": max_frames,
            "expected_frames": frames,
            "output_fps": output_fps,
            "estimated_video_seconds": est_seconds,
            "estimated_video_minutes": est_minutes,
            "estimated_storage_mb": est_storage_mb,
            "estimated_storage_gb": round(est_storage_mb / 1024.0, 2),
            "notes": [
                "10-minute cadence captures canopy and flower development without overloading storage.",
                "Target output of roughly 4-8 minutes keeps weekly changes visible.",
                "Use stable camera position and fixed lights-on capture window for best comparisons.",
            ],
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
                frame = cls._auto_tune_exposure(frame)
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
                lights_on_only = bool(cls._tl_state.get("lights_on_only", cls._default_lights_on_only))

            if not session_dir:
                cls._tl_state["last_error"] = "missing_session_dir"
                time.sleep(1)
                continue

            allowed = cls._capture_allowed_now(lights_on_only=lights_on_only)
            out = None
            if allowed.get("allowed", True):
                out = cls._write_frame(Path(session_dir), frame_no=frame_no, quality=quality)
            now = time.time()

            with cls._tl_lock:
                if out:
                    cls._tl_state["frame_count"] = frame_no
                    cls._tl_state["last_capture_ts"] = now
                    cls._tl_state["last_frame"] = out
                    cls._tl_state["last_skip_reason"] = None
                    cls._tl_state["last_error"] = None
                else:
                    if not allowed.get("allowed", True):
                        cls._tl_state["last_skip_reason"] = str(allowed.get("reason", "capture_skipped"))
                        cls._tl_state["skipped_captures"] = int(cls._tl_state.get("skipped_captures", 0)) + 1
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
        cap = cls._capture_allowed_now(lights_on_only=bool(st.get("lights_on_only", cls._default_lights_on_only)))
        st["capture_allowed_now"] = bool(cap.get("allowed", True))
        st["capture_policy_reason"] = cap.get("reason", "always")
        if "window" in cap:
            st["capture_window"] = cap.get("window")
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
                    "lights_on_only": valid["lights_on_only"],
                    "label": valid["label"],
                    "session_id": session_id,
                    "session_dir": str(session_dir),
                    "frame_count": 0,
                    "skipped_captures": 0,
                    "last_capture_ts": None,
                    "last_frame": None,
                    "last_skip_reason": None,
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
        if cls._cv2 is None or cls._cap is None:
            return None

        q = max(40, min(95, cls._default_snapshot_quality))
        with cls._lock:
            try:
                ret, frame = cls._cap.read()
                if ret and frame is not None:
                    frame = cls._auto_tune_exposure(frame)
                    ok, jpeg = cls._cv2.imencode(".jpg", frame, [int(cls._cv2.IMWRITE_JPEG_QUALITY), int(q)])
                    if ok:
                        return jpeg.tobytes()
            except Exception as e:
                cls.last_error = f"snapshot_error: {e}"
        return None

    @classmethod
    def is_healthy(cls) -> bool:
        return cls._is_open()

    @classmethod
    def mjpeg_generator(cls, fps: int = 10, quality: int = 85, width: Optional[int] = None, height: Optional[int] = None):
        """Lightweight MJPEG streaming generator for /camera/stream endpoint.
        Uses OpenCV frame capture with configurable FPS throttling."""
        import time
        if not cls._is_open() and not cls.ensure_ready():
            yield b''
            return
        if cls._cap is None:
            yield b''
            return
        
        fps = max(2, min(24, int(fps)))
        quality = max(40, min(95, int(quality)))
        target_w = int(width) if width else None
        target_h = int(height) if height else None
        if target_w is not None:
            target_w = max(320, min(1920, target_w))
        if target_h is not None:
            target_h = max(240, min(1080, target_h))

        frame_delay = 1.0 / fps
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

                    frame = cls._auto_tune_exposure(frame)

                    if target_w and target_h:
                        frame = cls._cv2.resize(frame, (target_w, target_h), interpolation=cls._cv2.INTER_AREA)
                    
                    # Encode frame as JPEG
                    ret, jpeg = cls._cv2.imencode('.jpg', frame, [int(cls._cv2.IMWRITE_JPEG_QUALITY), int(quality)])
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

    @classmethod
    def analyze_timelapse(cls, session_id: Optional[str] = None, sample_frames: int = 8) -> Dict[str, Any]:
        if cls._cv2 is None and not cls._import_drivers():
            return {"ok": False, "error": "opencv_unavailable"}

        cls._ensure_store_dir()
        target_dir: Optional[Path] = None
        if session_id:
            candidate = cls._store_dir / str(session_id)
            if candidate.exists() and candidate.is_dir():
                target_dir = candidate
        if target_dir is None:
            sessions = cls.list_sessions(limit=20)
            for s in sessions:
                if int(s.get("frames", 0)) >= 2:
                    target_dir = Path(s["path"])
                    break
            if target_dir is None and sessions:
                target_dir = Path(sessions[0]["path"])

        if target_dir is None:
            return {"ok": False, "error": "no_sessions"}

        frames = sorted(target_dir.glob("frame_*.jpg"))
        if len(frames) < 2:
            return {"ok": False, "error": "insufficient_frames", "session_id": target_dir.name, "frames": len(frames)}

        sample_frames = max(3, min(24, int(sample_frames)))
        if len(frames) <= sample_frames:
            picked = frames
        else:
            idxs = sorted({int(round(i * (len(frames) - 1) / float(sample_frames - 1))) for i in range(sample_frames)})
            picked = [frames[i] for i in idxs]

        brightness_vals = []
        contrast_vals = []
        blur_vals = []
        green_vals = []

        for fp in picked:
            img = cls._cv2.imread(str(fp))
            if img is None:
                continue
            h, w = img.shape[:2]
            y0 = int(h * 0.1)
            y1 = int(h * 0.9)
            x0 = int(w * 0.1)
            x1 = int(w * 0.9)
            roi = img[y0:y1, x0:x1]
            if roi.size == 0:
                continue

            gray = cls._cv2.cvtColor(roi, cls._cv2.COLOR_BGR2GRAY)
            hsv = cls._cv2.cvtColor(roi, cls._cv2.COLOR_BGR2HSV)
            green_mask = cls._cv2.inRange(hsv, (35, 35, 30), (95, 255, 255))

            brightness_vals.append(float(gray.mean()))
            contrast_vals.append(float(gray.std()))
            blur_vals.append(float(cls._cv2.Laplacian(gray, cls._cv2.CV_64F).var()))
            green_vals.append(float((green_mask > 0).sum()) / float(green_mask.size))

        if len(green_vals) < 2:
            return {"ok": False, "error": "analysis_failed", "session_id": target_dir.name}

        mean_brightness = sum(brightness_vals) / len(brightness_vals)
        mean_contrast = sum(contrast_vals) / len(contrast_vals)
        mean_blur = sum(blur_vals) / len(blur_vals)
        mean_green = sum(green_vals) / len(green_vals)
        green_delta = green_vals[-1] - green_vals[0]

        observations = []
        recommendations = []
        confidence = 0.8

        if mean_blur < 80:
            observations.append("Image sharpness is low; fine flower detail is likely being lost.")
            recommendations.append("Refocus the lens and keep camera rigid to reduce blur in timelapse frames.")
            confidence -= 0.1
        else:
            observations.append("Image sharpness is good enough to track flower structure over time.")

        if mean_brightness < 60:
            observations.append("Canopy appears underexposed.")
            recommendations.append("Increase grow-light period capture brightness or add fixed supplemental fill light.")
            confidence -= 0.1
        elif mean_brightness > 200:
            observations.append("Canopy appears overexposed.")
            recommendations.append("Lower exposure or reduce direct glare to preserve bud and leaf texture.")
            confidence -= 0.1
        else:
            observations.append("Exposure is in a usable range for visual comparisons.")

        if green_delta > 0.03:
            observations.append("Visible canopy expansion trend detected across sampled frames.")
        elif green_delta < -0.02:
            observations.append("Green canopy coverage appears to be declining.")
            recommendations.append("Inspect for nutrient, pH, or light stress if this decline persists for multiple days.")
            confidence -= 0.1
        else:
            observations.append("Canopy coverage trend is mostly stable in this sample window.")

        if mean_contrast < 22:
            recommendations.append("Increase scene contrast by stabilizing camera angle and reducing lens haze or condensation.")

        if not recommendations:
            recommendations.append("Keep the camera fixed, capture during consistent lighting, and review trend snapshots weekly.")

        score = max(0, min(100, int(round(65 + (mean_green * 50) + (green_delta * 300) + min(mean_blur, 180) / 6.0))))

        return {
            "ok": True,
            "session_id": target_dir.name,
            "sampled_frames": len(green_vals),
            "frames_total": len(frames),
            "metrics": {
                "green_ratio_mean": round(mean_green, 4),
                "green_ratio_delta": round(green_delta, 4),
                "brightness_mean": round(mean_brightness, 1),
                "contrast_mean": round(mean_contrast, 1),
                "sharpness_laplacian_var": round(mean_blur, 1),
            },
            "grow_feedback": {
                "visual_progress_score": score,
                "confidence": round(max(0.4, min(0.95, confidence)), 2),
                "observations": observations,
                "recommendations": recommendations,
                "disclaimer": "Heuristic vision-only feedback. Confirm plant health with pH, EC, temperature, and in-person inspection.",
            },
        }
