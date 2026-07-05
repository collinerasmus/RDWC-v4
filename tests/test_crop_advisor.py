import importlib
import sqlite3
from datetime import date


def _load_module(monkeypatch, tmp_path):
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
            (5, "veg", 1.3, 5.8, 6.2, "veg baseline"),
        )
        conn.commit()


def _seed_schedule_current_and_next(db_path):
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


def test_advisor_flags_ec_below_target(monkeypatch, tmp_path):
    advisor, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schedule(db_path)

    monkeypatch.setattr(
        advisor,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "targets.ec_target": "1.3",
            "targets.ph_low": "5.8",
            "targets.ph_high": "6.2",
        },
    )

    monkeypatch.setattr(
        advisor,
        "_sensor_snapshot",
        lambda: {
            "online": True,
            "age_seconds": 12,
            "ec_mscm": 0.95,
            "ph": 5.95,
            "temperature_c": 19.2,
            "ts": "2026-07-05T08:00:00Z",
            "errors": {},
        },
    )
    monkeypatch.setattr(
        advisor,
        "_ndi_snapshot",
        lambda history_days=14: {
            "latest_value": 50.0,
            "previous_value": 60.0,
            "trend": "falling",
            "seven_day_average_ml": 55.0,
            "history_days": 14,
            "history_values": [70, 60, 55, 50],
            "avg3": 55.0,
            "avg7": 58.0,
        },
    )

    payload = advisor.generate_advisor_payload()
    codes = [r["code"] for r in payload["recommendations"]]
    assert "EC_BELOW_TARGET" in codes


def test_advisor_flags_stale_sensors_first(monkeypatch, tmp_path):
    advisor, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schedule(db_path)

    monkeypatch.setattr(
        advisor,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "targets.ec_target": "1.3",
            "targets.ph_low": "5.8",
            "targets.ph_high": "6.2",
        },
    )
    monkeypatch.setattr(
        advisor,
        "_sensor_snapshot",
        lambda: {
            "online": False,
            "age_seconds": 500,
            "ec_mscm": None,
            "ph": None,
            "temperature_c": None,
            "ts": None,
            "errors": {"stale": "reading is 500s old"},
        },
    )

    payload = advisor.generate_advisor_payload()
    recs = payload["recommendations"]
    assert recs
    assert recs[0]["code"] == "SENSOR_STALE"


def test_advisor_reports_on_track(monkeypatch, tmp_path):
    advisor, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schedule(db_path)

    class _FixedDate:
        def date(self):
            return date(2026, 7, 5)

    monkeypatch.setattr(
        advisor,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "targets.ec_target": "1.3",
            "targets.ph_low": "5.8",
            "targets.ph_high": "6.2",
        },
    )
    monkeypatch.setattr(
        advisor,
        "_sensor_snapshot",
        lambda: {
            "online": True,
            "age_seconds": 14,
            "ec_mscm": 1.31,
            "ph": 6.0,
            "temperature_c": 19.1,
            "ts": "2026-07-05T08:00:00Z",
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
            "seven_day_average_ml": 50.0,
            "history_days": 14,
            "history_values": [50] * 14,
            "avg3": 50.0,
            "avg7": 50.0,
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
    assert payload["overview"]["verdict"] == "steady"
    assert payload["assessors"]["sensors"]["status"] == "good"
    assert payload["recommendations"] == []


def test_advisor_defers_mild_changes_when_rollover_is_soon(monkeypatch, tmp_path):
    advisor, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schedule_current_and_next(db_path)

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
    codes = [r["code"] for r in payload["recommendations"]]

    assert "ROLLOVER_IMMINENT" in codes
    assert "EC_BELOW_TARGET" not in codes
    assert payload["overview"]["verdict"] == "hold"
    assert "PH_HIGH" not in codes
