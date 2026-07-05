import importlib
import sqlite3
from datetime import date


def _load_engine(monkeypatch, tmp_path):
    db_path = tmp_path / "rdwc.sqlite"
    monkeypatch.setenv("RDWC_DB", str(db_path))
    import app.services.advisor_engine as advisor

    return importlib.reload(advisor), db_path


def _seed_schedule(db_path):
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE nutrient_schedule (
                week INTEGER PRIMARY KEY,
                phase TEXT NOT NULL,
                grow_ml10 REAL NOT NULL DEFAULT 0,
                micro_ml10 REAL NOT NULL DEFAULT 0,
                bloom_ml10 REAL NOT NULL DEFAULT 0,
                ec_target REAL NOT NULL DEFAULT 1.0,
                ph_low REAL NOT NULL DEFAULT 5.8,
                ph_high REAL NOT NULL DEFAULT 6.2,
                temp_target REAL NOT NULL DEFAULT 20.0,
                lights TEXT NOT NULL DEFAULT '18/6',
                notes TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO nutrient_schedule(week, phase, ec_target, ph_low, ph_high, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (4, "flower", 2.1, 5.8, 5.8, "current week"),
        )
        conn.execute(
            "INSERT INTO nutrient_schedule(week, phase, ec_target, ph_low, ph_high, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (5, "flower", 2.4, 5.8, 5.8, "next week"),
        )
        conn.commit()


def test_overview_holds_when_rollover_is_soon(monkeypatch, tmp_path):
    advisor, db_path = _load_engine(monkeypatch, tmp_path)
    _seed_schedule(db_path)

    monkeypatch.setattr(
        advisor,
        "_schedule_timing_context",
        lambda: {
            "current_week": 4,
            "lights_on_time": "15:00",
            "now_local": "2026-07-05T10:00:00+02:00",
            "next_rollover_local": "2026-07-05T15:00:00+02:00",
            "hours_to_rollover": 5.0,
            "rollover_soon": True,
        },
    )
    monkeypatch.setattr(
        advisor,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-07",
            "targets.ec_target": "2.1",
            "targets.ph_low": "5.8",
            "targets.ph_high": "5.8",
        },
    )
    monkeypatch.setattr(
        advisor,
        "_sensor_snapshot",
        lambda: {
            "online": True,
            "age_seconds": 9,
            "ec_mscm": 2.11,
            "ph": 5.82,
            "temperature_c": 18.255,
            "ts": "2026-07-05T10:00:00+02:00",
            "errors": {},
        },
    )
    monkeypatch.setattr(
        advisor,
        "_ndi_snapshot",
        lambda history_days=14: {
            "latest_value": 50.0,
            "previous_value": 50.0,
            "trend": "stable",
            "seven_day_average_ml": 67.143,
            "history_days": 28,
            "history_values": [50.0] * 28,
            "avg3": 50.0,
            "avg7": 67.143,
        },
    )
    monkeypatch.setattr(
        advisor,
        "_camera_snapshot",
        lambda: {
            "available": True,
            "mode": "libcamera",
            "camera_index": 0,
            "last_error": None,
            "status": "good",
            "summary": "Camera snapshot looks usable.",
            "brightness": 90.0,
            "edge_strength": 12.0,
            "color_balance": {"r": 90.0, "g": 88.0, "b": 84.0},
            "recommendations": [],
        },
    )

    payload = advisor.generate_advisor_payload()

    assert payload["overview"]["verdict"] == "hold"
    assert payload["assessors"]["schedule"]["defer_small_actions"] is True
    assert payload["assessors"]["camera"]["status"] == "good"
    assert payload["recommendations"][0]["code"] == "ROLLOVER_IMMINENT"


def test_camera_assessor_flags_dark_snapshot(monkeypatch, tmp_path):
    advisor, db_path = _load_engine(monkeypatch, tmp_path)
    _seed_schedule(db_path)

    monkeypatch.setattr(advisor, "_camera_snapshot", lambda: {
        "available": True,
        "mode": "libcamera",
        "camera_index": 0,
        "last_error": None,
        "status": "warn",
        "summary": "Camera snapshot is quite dark; plant detail may be hard to judge.",
        "brightness": 30.0,
        "edge_strength": 4.0,
        "color_balance": {"r": 31.0, "g": 30.0, "b": 29.0},
        "recommendations": [{
            "code": "CAMERA_DARK",
            "severity": "low",
            "confidence": 0.83,
            "title": "Camera image is underexposed",
            "action": "Check lighting, camera exposure, and lens cleanliness before relying on visual assessment.",
            "rationale": "Mean brightness is low in the latest snapshot.",
            "metrics": {"brightness": 30.0, "edge_strength": 4.0},
        }],
    })

    assessor = advisor._assess_camera({"rollover_soon": False})

    assert assessor["status"] == "warn"
    assert assessor["recommendations"][0]["code"] == "CAMERA_DARK"
