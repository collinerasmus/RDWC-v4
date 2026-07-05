from __future__ import annotations

import io
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

DB_PATH = Path(os.environ.get("RDWC_DB", str(Path(__file__).resolve().parents[2] / "data" / "rdwc.db")))


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _read_settings() -> Dict[str, str]:
    try:
        from app.settings import get_all_settings

        return get_all_settings() or {}
    except Exception:
        return {}


def _grow_context() -> Dict[str, Any]:
    settings = _read_settings()
    start_raw = str(settings.get("general.grow_start_date", "") or "").strip()
    if not start_raw:
        return {"grow_start_date": None, "grow_day": None, "grow_week": 1}

    try:
        start_day = datetime.strptime(start_raw, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        elapsed = max(0, (today - start_day).days)
        return {
            "grow_start_date": start_raw,
            "grow_day": elapsed + 1,
            "grow_week": min(12, (elapsed // 7) + 1),
        }
    except Exception:
        return {"grow_start_date": None, "grow_day": None, "grow_week": 1}


def _schedule_timing_context() -> Dict[str, Any]:
    timing: Dict[str, Any] = {
        "current_week": 1,
        "lights_on_time": "15:00",
        "now_local": None,
        "next_rollover_local": None,
        "hours_to_rollover": None,
        "rollover_soon": False,
    }
    try:
        from app.schedule_api import _get_week_timing_info

        raw = _get_week_timing_info() or {}
        timing["current_week"] = int(raw.get("current_week") or 1)
        timing["lights_on_time"] = str(raw.get("lights_on_time") or "15:00")
        timing["now_local"] = raw.get("now_local")
        timing["next_rollover_local"] = raw.get("next_rollover_local")
        rollover_raw = raw.get("next_rollover_local")
        if rollover_raw:
            rollover_dt = datetime.fromisoformat(str(rollover_raw))
            now_dt = datetime.now(timezone.utc).astimezone(rollover_dt.tzinfo or timezone.utc)
            hours = round((rollover_dt - now_dt).total_seconds() / 3600.0, 2)
            timing["hours_to_rollover"] = max(0.0, hours)
            timing["rollover_soon"] = hours <= 6.0
    except Exception:
        pass
    return timing


def _schedule_for_week(week: int) -> Dict[str, Any]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = None
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT week, phase, ec_target, ph_low, ph_high, notes
                FROM nutrient_schedule
                WHERE week = ?
                LIMIT 1
                """,
                (int(week),),
            ).fetchone()
            if not row:
                row = conn.execute(
                    """
                    SELECT week, phase, ec_target, ph_low, ph_high, notes
                    FROM nutrient_schedule
                    ORDER BY week DESC
                    LIMIT 1
                    """,
                ).fetchone()
    except Exception:
        row = None

    settings = _read_settings()
    return {
        "week": int(row["week"]) if row and row["week"] is not None else int(week),
        "phase": str(row["phase"]) if row and row["phase"] is not None else "unknown",
        "ec_target": _to_float(row["ec_target"] if row else settings.get("targets.ec_target"), 0.0),
        "ph_low": _to_float(row["ph_low"] if row else settings.get("targets.ph_low"), 5.8),
        "ph_high": _to_float(row["ph_high"] if row else settings.get("targets.ph_high"), 6.2),
        "notes": str(row["notes"]) if row and row["notes"] is not None else "",
    }


def _sensor_snapshot() -> Dict[str, Any]:
    try:
        from app.sensors_core import read_sensors_from_db

        d = read_sensors_from_db(max_age_sec=120)
        return {
            "online": bool(d.get("online")),
            "age_seconds": d.get("age_sec"),
            "ec_mscm": _to_float(d.get("ec_mscm")),
            "ph": _to_float(d.get("ph")),
            "temperature_c": _to_float(d.get("temperature_c")),
            "ts": d.get("ts"),
            "errors": d.get("errors") or {},
        }
    except Exception as exc:
        return {"online": False, "age_seconds": None, "ec_mscm": None, "ph": None, "temperature_c": None, "ts": None, "errors": {"sensor": str(exc)}}


def _ndi_snapshot(history_days: int = 14) -> Dict[str, Any]:
    try:
        from app.services.nutrient_demand import get_latest_ndi, get_ndi_history

        latest = get_latest_ndi() or {}
        hist = get_ndi_history(max(3, int(history_days)))
    except Exception:
        latest = {}
        hist = []

    values = [_to_float(row.get("total_nutrient_ml"), 0.0) or 0.0 for row in hist if isinstance(row, dict)]
    last3 = values[-3:] if len(values) >= 3 else values
    last7 = values[-7:] if len(values) >= 7 else values
    avg3 = round(sum(last3) / len(last3), 3) if last3 else 0.0
    avg7 = round(sum(last7) / len(last7), 3) if last7 else 0.0

    return {
        "latest_value": _to_float(latest.get("latest_value"), 0.0) or 0.0,
        "previous_value": _to_float(latest.get("previous_value")),
        "trend": str(latest.get("trend") or "unknown"),
        "seven_day_average_ml": _to_float(latest.get("seven_day_average_ml"), 0.0) or 0.0,
        "history_days": len(values),
        "history_values": values,
        "avg3": avg3,
        "avg7": avg7,
    }


def _camera_snapshot() -> Dict[str, Any]:
    try:
        from PIL import Image, ImageFilter, ImageStat  # type: ignore
        from app.camera import CameraManager
        from app.relays_core import get_relay_status

        status = CameraManager.status() or {}
        available = bool(status.get("available"))
        mode = str(status.get("mode") or "unavailable")
        last_error = status.get("last_error")
        relay_status = get_relay_status() or {}
        lights_state = bool((relay_status.get("lights") or {}).get("state"))

        result: Dict[str, Any] = {
            "available": available,
            "mode": mode,
            "camera_index": status.get("camera_index"),
            "last_error": last_error,
            "lights_on": lights_state,
            "visual_ok": False,
            "brightness": None,
            "edge_strength": None,
            "color_balance": None,
        }

        frame = CameraManager.capture_single_frame() if available else None
        if not frame:
            result["status"] = "warn" if available else "bad"
            result["summary"] = "Camera available but no snapshot could be captured." if available else "Camera unavailable or not initialized."
            return result

        img = Image.open(io.BytesIO(frame)).convert("RGB")
        gray = img.convert("L")
        stat = ImageStat.Stat(gray)
        brightness = float(stat.mean[0])
        edge_img = img.convert("L").filter(ImageFilter.FIND_EDGES)
        edge_strength = float(ImageStat.Stat(edge_img).mean[0])
        rgb = ImageStat.Stat(img).mean
        color_balance = {
            "r": round(float(rgb[0]), 1),
            "g": round(float(rgb[1]), 1),
            "b": round(float(rgb[2]), 1),
        }

        result.update(
            _camera_assessment_from_snapshot({
                **result,
                "brightness": round(brightness, 1),
                "edge_strength": round(edge_strength, 1),
                "color_balance": color_balance,
            })
        )
        return result
    except Exception as exc:
        return {
            "available": False,
            "mode": "unavailable",
            "camera_index": None,
            "last_error": str(exc),
            "status": "bad",
            "visual_ok": False,
            "summary": "Camera assessment unavailable.",
            "recommendations": [{
                "code": "CAMERA_ERROR",
                "severity": "low",
                "confidence": 0.75,
                "title": "Camera assessment unavailable",
                "action": "Check camera drivers and live-feed readiness.",
                "rationale": str(exc),
                "metrics": {},
            }],
        }


def _camera_assessment_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    lights_state = bool(snapshot.get("lights_on"))
    brightness = _to_float(snapshot.get("brightness"), 0.0) or 0.0
    edge_strength = _to_float(snapshot.get("edge_strength"), 0.0) or 0.0

    status_flag = "good"
    summary = "Camera snapshot looks usable."
    recommendations: List[Dict[str, Any]] = []

    if brightness < 40:
        if lights_state:
            status_flag = "warn"
            summary = "Camera snapshot is quite dark while the lights are on; plant detail may be hard to judge."
            recommendations.append({
                "code": "CAMERA_DARK",
                "severity": "low",
                "confidence": 0.83,
                "title": "Camera image is underexposed",
                "action": "Check lighting, camera exposure, and lens cleanliness before relying on visual assessment.",
                "rationale": "Mean brightness is low while the lights relay is on.",
                "metrics": {"brightness": round(brightness, 1), "edge_strength": round(edge_strength, 1), "lights_on": lights_state},
            })
        else:
            status_flag = "info"
            summary = "Camera image is dark because the grow lights are off; that is expected after lights-out."
            recommendations.append({
                "code": "CAMERA_LIGHTS_OFF",
                "severity": "info",
                "confidence": 0.96,
                "title": "Dark camera image is expected with lights off",
                "action": "Use the next lights-on window for visual assessment.",
                "rationale": "The lights relay is off, so a dark snapshot is expected.",
                "metrics": {"brightness": round(brightness, 1), "edge_strength": round(edge_strength, 1), "lights_on": lights_state},
            })
    elif brightness > 210:
        status_flag = "warn"
        summary = "Camera snapshot is very bright; highlights may be clipping."
        recommendations.append({
            "code": "CAMERA_BRIGHT",
            "severity": "low",
            "confidence": 0.82,
            "title": "Camera image is overexposed",
            "action": "Reduce exposure or adjust lighting so leaf detail remains visible.",
            "rationale": "Mean brightness is high in the latest snapshot.",
            "metrics": {"brightness": round(brightness, 1), "edge_strength": round(edge_strength, 1), "lights_on": lights_state},
        })

    if edge_strength < 6.0:
        if lights_state:
            status_flag = "warn" if status_flag == "good" else status_flag
            summary = "Camera detail is low; image may be soft or out of focus."
            recommendations.append({
                "code": "CAMERA_SOFT",
                "severity": "low",
                "confidence": 0.78,
                "title": "Camera detail is soft",
                "action": "Check focus, vibration, condensation, and lens obstruction.",
                "rationale": "Edge strength is low while the lights relay is on.",
                "metrics": {"brightness": round(brightness, 1), "edge_strength": round(edge_strength, 1), "lights_on": lights_state},
            })
        elif status_flag == "good":
            status_flag = "info"
            summary = "Camera detail is low while the lights are off; that is expected and not a camera fault."
            recommendations.append({
                "code": "CAMERA_EXPECTED_DARK",
                "severity": "info",
                "confidence": 0.96,
                "title": "Low detail is expected when lights are off",
                "action": "Reassess camera detail after lights-on.",
                "rationale": "Edge strength is low because the grow area is unlit.",
                "metrics": {"brightness": round(brightness, 1), "edge_strength": round(edge_strength, 1), "lights_on": lights_state},
            })

    return {
        "status": status_flag,
        "visual_ok": True,
        "summary": summary,
        "recommendations": recommendations,
    }


def _recommend(code: str, severity: str, confidence: float, title: str, action: str, rationale: str, metrics: Optional[Dict[str, Any]] = None, source: str = "overview") -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "title": title,
        "action": action,
        "rationale": rationale,
        "metrics": metrics or {},
        "source": source,
    }


def _assess_schedule(grow: Dict[str, Any], timing: Dict[str, Any], current: Dict[str, Any], nxt: Dict[str, Any]) -> Dict[str, Any]:
    rollover_soon = bool(timing.get("rollover_soon"))
    hours_to_rollover = timing.get("hours_to_rollover")
    if rollover_soon:
        summary = f"Current week rolls over in about {hours_to_rollover} hours; hold small changes until then."
        status = "info"
    else:
        summary = f"Current week {current.get('week')} is active and the schedule is stable."
        status = "good"

    recommendations: List[Dict[str, Any]] = []
    if rollover_soon:
        recommendations.append(_recommend(
            "ROLLOVER_IMMINENT",
            "info",
            0.99,
            "Scheduled setpoint change is imminent",
            f"Hold non-essential corrections until the rollover at {timing.get('next_rollover_local')}; then reassess against week {nxt.get('week')}.",
            "The active schedule is about to change, so advice should defer mild corrections.",
            {"hours_to_rollover": hours_to_rollover, "current_week": current.get("week"), "next_week": nxt.get("week")},
            source="schedule",
        ))

    return {
        "name": "schedule",
        "status": status,
        "score": 92 if rollover_soon else 98,
        "summary": summary,
        "evidence": {
            "grow_day": grow.get("grow_day"),
            "current_week": current.get("week"),
            "next_week": nxt.get("week"),
            "lights_on_time": timing.get("lights_on_time"),
            "next_rollover_local": timing.get("next_rollover_local"),
            "hours_to_rollover": hours_to_rollover,
        },
        "recommendations": recommendations,
        "defer_small_actions": rollover_soon,
    }


def _assess_sensors(sensor: Dict[str, Any], current: Dict[str, Any], timing: Dict[str, Any]) -> Dict[str, Any]:
    ec = _to_float(sensor.get("ec_mscm"))
    ph = _to_float(sensor.get("ph"))
    temp = _to_float(sensor.get("temperature_c"))
    online = bool(sensor.get("online"))
    age = sensor.get("age_seconds")

    recommendations: List[Dict[str, Any]] = []
    if not online:
        recommendations.append(_recommend(
            "SENSOR_STALE",
            "high",
            0.95,
            "Restore fresh sensor data before dosing decisions",
            "Check sensor poller health and wiring, then verify /api/sensors reports online=true and age<60s.",
            "Reliable EC/pH guidance requires fresh sensor input.",
            {"age_seconds": age},
            source="sensors",
        ))
        return {
            "name": "sensors",
            "status": "bad",
            "score": 20,
            "summary": "Sensor data is stale or unavailable.",
            "evidence": sensor,
            "recommendations": recommendations,
        }

    status = "good"
    score = 95
    current_ec = _to_float(current.get("ec_target"), 0.0) or 0.0
    current_ph_low = _to_float(current.get("ph_low"), 5.8) or 5.8
    current_ph_high = _to_float(current.get("ph_high"), 6.2) or 6.2
    if ec is not None and abs(ec - current_ec) > 0.2:
        status = "warn"
        score = 80
    if ph is not None and (ph < current_ph_low - 0.15 or ph > current_ph_high + 0.15):
        status = "warn" if status == "good" else status
        score = min(score, 78)
    if temp is not None and (temp < 15 or temp > 24):
        status = "warn" if status == "good" else status
        score = min(score, 75)

    summary = "Fresh sensor data is available and numerically sane."
    if status == "warn":
        summary = "Fresh sensors are available, but one or more readings are drifting away from the current schedule band."

    recommendations = []
    if ec is not None and ec < current_ec - 0.15:
        recommendations.append(_recommend(
            "EC_BELOW_TARGET",
            "medium",
            0.84,
            "EC is below schedule target",
            "Increase nutrient strength on the next mix and verify dosing calibration rates.",
            "Current EC is materially below the active schedule target.",
            {"ec": round(ec, 3), "ec_target": round(current_ec, 3), "delta": round(ec - current_ec, 3)},
            source="sensors",
        ))
    if ec is not None and ec > current_ec + 0.2:
        recommendations.append(_recommend(
            "EC_ABOVE_TARGET",
            "medium",
            0.86,
            "EC is above schedule target",
            "Dilute with pH-balanced water in small steps and re-check EC after full mixing.",
            "Current EC is above the active schedule target.",
            {"ec": round(ec, 3), "ec_target": round(current_ec, 3), "delta": round(ec - current_ec, 3)},
            source="sensors",
        ))

    if ph is not None and ph < current_ph_low - 0.05:
        recommendations.append(_recommend(
            "PH_LOW",
            "medium",
            0.82,
            "pH is below schedule range",
            "Apply a small pH-up correction and confirm probe calibration if the drift persists.",
            "Current pH is below the active schedule band.",
            {"ph": round(ph, 3), "ph_low": round(current_ph_low, 3), "ph_high": round(current_ph_high, 3)},
            source="sensors",
        ))
    if ph is not None and ph > current_ph_high + 0.05:
        recommendations.append(_recommend(
            "PH_HIGH",
            "medium",
            0.82,
            "pH is above schedule range",
            "Investigate alkalinity drift and adjust toward target band with measured correction.",
            "Current pH is above the active schedule band.",
            {"ph": round(ph, 3), "ph_low": round(current_ph_low, 3), "ph_high": round(current_ph_high, 3)},
            source="sensors",
        ))

    return {
        "name": "sensors",
        "status": status,
        "score": score,
        "summary": summary,
        "evidence": sensor,
        "recommendations": recommendations,
    }


def _assess_ndi(ndi: Dict[str, Any], current: Dict[str, Any], timing: Dict[str, Any]) -> Dict[str, Any]:
    avg3 = _to_float(ndi.get("avg3"), 0.0) or 0.0
    avg7 = _to_float(ndi.get("avg7"), 0.0) or 0.0
    trend = str(ndi.get("trend") or "unknown")
    rollover_soon = bool(timing.get("rollover_soon"))

    recommendations: List[Dict[str, Any]] = []
    status = "good"
    score = 95
    summary = "NDI trend is stable relative to recent history."

    if avg7 > 0 and avg3 > avg7 * 1.35:
        status = "warn"
        score = 78
        summary = "NDI is spiking relative to recent baseline."
        recommendations.append(_recommend(
            "NDI_SPIKE",
            "low",
            0.74,
            "Nutrient demand is spiking vs recent baseline",
            "Check reservoir top-ups, verify dosing logs, and confirm this aligns with the current phase transition.",
            "3-day NDI average is significantly above the 7-day baseline.",
            {"ndi_avg3": round(avg3, 3), "ndi_avg7": round(avg7, 3)},
            source="ndi",
        ))
    elif avg7 > 0 and avg3 < avg7 * 0.65:
        status = "warn"
        score = 80
        summary = "NDI is below recent baseline."
        recommendations.append(_recommend(
            "NDI_DROP",
            "low",
            0.72,
            "Nutrient demand is below recent baseline",
            "Confirm plant uptake trend, EC sensor stability, and that the current schedule week target is still appropriate.",
            "3-day NDI average is significantly below the 7-day baseline.",
            {"ndi_avg3": round(avg3, 3), "ndi_avg7": round(avg7, 3)},
            source="ndi",
        ))

    if rollover_soon:
        summary = "NDI is being compared against an imminent schedule rollover, so only severe deviations should prompt action now."

    return {
        "name": "ndi",
        "status": status,
        "score": score,
        "summary": summary,
        "evidence": {
            "latest_value": ndi.get("latest_value"),
            "trend": trend,
            "avg3": avg3,
            "avg7": avg7,
            "history_days": ndi.get("history_days"),
        },
        "recommendations": recommendations,
    }


def _assess_camera(timing: Dict[str, Any]) -> Dict[str, Any]:
    snap = _camera_snapshot()
    recs = list(snap.get("recommendations") or [])
    rollover_soon = bool(timing.get("rollover_soon"))
    status = str(snap.get("status") or "bad")
    score = 30 if status == "bad" else 72 if status == "warn" else 92
    summary = str(snap.get("summary") or "Camera assessment unavailable.")
    if rollover_soon and status == "good":
        summary = "Camera is healthy; visual checks can wait until after the scheduled rollover if the crop is otherwise stable."

    return {
        "name": "camera",
        "status": status,
        "score": score,
        "summary": summary,
        "evidence": {
            "available": snap.get("available"),
            "mode": snap.get("mode"),
            "camera_index": snap.get("camera_index"),
            "brightness": snap.get("brightness"),
            "edge_strength": snap.get("edge_strength"),
            "color_balance": snap.get("color_balance"),
            "last_error": snap.get("last_error"),
        },
        "recommendations": recs,
    }


def _build_overview(assessors: Dict[str, Dict[str, Any]], timing: Dict[str, Any], current: Dict[str, Any], nxt: Dict[str, Any]) -> Dict[str, Any]:
    if not assessors:
        return {
            "verdict": "unknown",
            "status": "bad",
            "confidence": 0.0,
            "title": "No assessments available",
            "summary": "Advisor could not build an assessment stack.",
            "action": "Check backend data sources and retry.",
            "reason_codes": [],
            "hours_to_rollover": timing.get("hours_to_rollover"),
        }

    severity_rank = {"bad": 3, "warn": 2, "info": 1, "good": 0}
    top = max(assessors.values(), key=lambda a: (severity_rank.get(a.get("status"), 0), float(a.get("score") or 0)))
    all_codes = []
    all_recs: List[Dict[str, Any]] = []
    for assessor in assessors.values():
        for rec in assessor.get("recommendations") or []:
            all_recs.append(rec)
            code = rec.get("code")
            if code:
                all_codes.append(code)

    status = top.get("status") or "info"
    if timing.get("rollover_soon") and top.get("name") == "schedule":
        verdict = "hold"
        title = "Hold changes until the scheduled rollover"
        summary = f"The next setpoint change is due in about {timing.get('hours_to_rollover')} hours, so only severe deviations warrant immediate action."
        action = f"Reassess after {timing.get('next_rollover_local')} using the next week's targets."
        confidence = 0.97
    elif status == "bad":
        verdict = "urgent"
        title = f"{top.get('name', 'system').capitalize()} needs attention"
        summary = str(top.get("summary") or "One or more assessors report a blocking issue.")
        action = str((top.get("recommendations") or [{}])[0].get("action") or "Address the highest-priority blocking issue first.")
        confidence = 0.94
    elif status == "warn":
        verdict = "watch"
        title = "Watch closely"
        summary = str(top.get("summary") or "There are non-blocking deviations that should be monitored.")
        action = str((top.get("recommendations") or [{}])[0].get("action") or "Monitor and re-evaluate after the next refresh.")
        confidence = 0.88
    else:
        verdict = "steady"
        title = "System is broadly on track"
        summary = "No major deviations were detected across sensors, schedule, NDI, or camera quality."
        action = "Continue current settings and revisit after the next rollover or if sensor readings drift."
        confidence = 0.91

    ranked = sorted(
        all_recs,
        key=lambda r: (severity_rank.get(str(r.get("severity") or "info"), 0), float(r.get("confidence") or 0)),
        reverse=True,
    )

    return {
        "verdict": verdict,
        "status": status,
        "confidence": confidence,
        "title": title,
        "summary": summary,
        "action": action,
        "reason_codes": list(dict.fromkeys(all_codes))[:8],
        "hours_to_rollover": timing.get("hours_to_rollover"),
        "current_week": current.get("week"),
        "next_week": nxt.get("week"),
        "top_recommendations": ranked[:4],
    }


def generate_advisor_payload() -> Dict[str, Any]:
    timing = _schedule_timing_context()
    grow = _grow_context()
    current_week = int(timing.get("current_week") or grow.get("grow_week") or 1)
    current = _schedule_for_week(current_week)
    nxt = _schedule_for_week(min(current_week + 1, 12))
    sensor = _sensor_snapshot()
    grow_days = int(grow.get("grow_day") or (current_week * 7))
    ndi = _ndi_snapshot(history_days=max(7, min(30, grow_days)))

    assessors: Dict[str, Dict[str, Any]] = {
        "schedule": _assess_schedule(grow, timing, current, nxt),
        "sensors": _assess_sensors(sensor, current, timing),
        "ndi": _assess_ndi(ndi, current, timing),
        "camera": _assess_camera(timing),
    }
    overview = _build_overview(assessors, timing, current, nxt)

    recommendations: List[Dict[str, Any]] = []
    for name, assessor in assessors.items():
        for rec in assessor.get("recommendations") or []:
            item = dict(rec)
            item.setdefault("source", name)
            recommendations.append(item)

    recommendations.sort(key=lambda r: (r.get("severity") == "high", r.get("severity") == "medium", float(r.get("confidence") or 0)), reverse=True)

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "advisor_version": "phase3-assessor-stack",
        "context": {
            "grow": grow,
            "timing": timing,
            "schedule": current,
            "next_schedule": nxt,
            "sensors": sensor,
            "ndi": ndi,
        },
        "assessors": assessors,
        "overview": overview,
        "recommendations": recommendations,
    }


@router.get("/api/advisor/overview")
def api_advisor_overview():
    try:
        payload = generate_advisor_payload()
        return {"ok": True, "overview": payload["overview"], "assessors": payload["assessors"], "generated_at": payload["generated_at"], "advisor_version": payload["advisor_version"]}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.get("/api/advisor/recommendations")
def api_advisor_recommendations():
    try:
        return generate_advisor_payload()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
