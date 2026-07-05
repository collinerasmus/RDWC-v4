import importlib
import sqlite3
from datetime import date


def _load_module(monkeypatch, tmp_path):
    db_path = tmp_path / "rdwc.sqlite"
    monkeypatch.setenv("RDWC_DB", str(db_path))
    import app.services.nutrient_demand as ndi

    return importlib.reload(ndi), db_path


def _seed_schema(db_path):
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE readings (
                ts INTEGER,
                ph REAL,
                ec_ms_cm REAL
            );

            CREATE TABLE dose_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                pump TEXT NOT NULL,
                seconds REAL NOT NULL,
                reason TEXT,
                actor TEXT,
                ph_before REAL,
                ph_after REAL,
                ec_before REAL,
                ec_after REAL,
                temp_c REAL,
                blocked_by TEXT,
                controller_state_json TEXT
            );

            CREATE TABLE nutrient_schedule (
                week INTEGER PRIMARY KEY,
                phase TEXT NOT NULL,
                grow_ml10 REAL NOT NULL DEFAULT 0,
                micro_ml10 REAL NOT NULL DEFAULT 0,
                bloom_ml10 REAL NOT NULL DEFAULT 0,
                ec_target REAL NOT NULL DEFAULT 1.0
            );
            """
        )
        conn.execute(
            "INSERT INTO nutrient_schedule(week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "seedling", 1.0, 1.0, 1.0, 0.8),
        )
        conn.execute(
            "INSERT INTO nutrient_schedule(week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "veg", 2.0, 2.0, 2.0, 1.2),
        )
        conn.commit()


def test_calculate_daily_ndi_uses_dose_events_and_sets_trend(monkeypatch, tmp_path):
    ndi, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schema(db_path)

    class _FixedNow:
        def date(self):
            return date(2026, 6, 11)

    monkeypatch.setattr(ndi, "_local_now", lambda: _FixedNow())

    monkeypatch.setattr(
        ndi,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "dosing.grow_ml_per_sec": "1.0",
            "dosing.micro_ml_per_sec": "1.0",
            "dosing.bloom_ml_per_sec": "1.0",
            "targets.ec_target": "0.8",
        },
    )

    prev_day = date(2026, 6, 9)
    today = date(2026, 6, 10)
    prev_start, _, _ = ndi._date_bounds(prev_day)
    today_start, _, _ = ndi._date_bounds(today)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)", (prev_start + 3600, "grow", 10))
        conn.execute("INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)", (prev_start + 7200, "micro", 2))
        conn.execute("INSERT INTO readings(ts, ph, ec_ms_cm) VALUES (?, ?, ?)", (prev_start + 3600, 5.8, 1.0))
        conn.execute("INSERT INTO readings(ts, ph, ec_ms_cm) VALUES (?, ?, ?)", (prev_start + 7200, 5.9, 1.4))
        conn.commit()

    prev_row = ndi.calculate_daily_ndi(prev_day.isoformat())
    assert prev_row["date"] == prev_day.isoformat()
    assert prev_row["total_nutrient_ml"] == 12.0
    assert prev_row["ec_target"] == 1.2
    assert prev_row["ndi_trend"] == "unknown"

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)", (today_start + 3600, "grow", 15))
        conn.execute("INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)", (today_start + 7200, "micro", 3))
        conn.execute("INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)", (today_start + 10800, "bloom", 1))
        conn.execute("INSERT INTO readings(ts, ph, ec_ms_cm) VALUES (?, ?, ?)", (today_start + 3600, 5.7, 1.2))
        conn.execute("INSERT INTO readings(ts, ph, ec_ms_cm) VALUES (?, ?, ?)", (today_start + 7200, 5.9, 1.6))
        conn.commit()

    today_row = ndi.calculate_daily_ndi(today.isoformat())
    assert today_row["date"] == today.isoformat()
    assert today_row["total_nutrient_ml"] == 19.0
    assert today_row["ndi_trend"] == "rising"

    history = ndi.get_ndi_history(2)
    assert [row["date"] for row in history] == [prev_day.isoformat(), today.isoformat()]


def test_calculate_daily_ndi_creates_zero_row_without_doses(monkeypatch, tmp_path):
    ndi, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schema(db_path)

    class _FixedNow:
        def date(self):
            return date(2026, 6, 12)

    monkeypatch.setattr(ndi, "_local_now", lambda: _FixedNow())

    monkeypatch.setattr(
        ndi,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "dosing.grow_ml_per_sec": "1.0",
            "dosing.micro_ml_per_sec": "1.0",
            "dosing.bloom_ml_per_sec": "1.0",
            "targets.ec_target": "0.8",
        },
    )

    row = ndi.calculate_daily_ndi("2026-06-11")
    assert row["total_nutrient_ml"] == 0.0
    assert row["dose_count"] == 0
    assert "no nutrient dosing recorded" in row["notes"]

    stored = ndi.get_latest_ndi()["latest"]
    assert stored is not None
    assert stored["date"] == "2026-06-11"
    assert stored["total_nutrient_ml"] == 0.0


def test_calculate_daily_ndi_uses_calibrated_rate_exactly(monkeypatch, tmp_path):
    ndi, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schema(db_path)
    monkeypatch.setattr(
        ndi,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "dosing.grow_ml_per_sec": "0.874",
            "dosing.micro_ml_per_sec": "0.874",
            "dosing.bloom_ml_per_sec": "0.874",
            "targets.ec_target": "0.8",
        },
    )

    day = date(2026, 6, 12)
    day_start, _, _ = ndi._date_bounds(day)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)",
            (day_start + 3600, "micro", 3.8138825324180012),
        )
        conn.execute(
            "INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)",
            (day_start + 3600, "bloom", 7.6277650648360025),
        )
        conn.commit()

    row = ndi.calculate_daily_ndi(day.isoformat())

    # 3.8138825324180012 * 0.874 ~= 3.3333333333333335 ml
    # 7.6277650648360025 * 0.874 ~= 6.666666666666667 ml
    assert row["micro_ml"] == 3.333
    assert row["bloom_ml"] == 6.667
    assert row["total_nutrient_ml"] == 10.0


def test_get_ndi_history_backfills_missing_days(monkeypatch, tmp_path):
    ndi, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schema(db_path)

    fake_today = date(2026, 6, 15)

    class _FixedNow:
        def date(self):
            return fake_today

    monkeypatch.setattr(ndi, "_local_now", lambda: _FixedNow())
    monkeypatch.setattr(
        ndi,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-01",
            "dosing.grow_ml_per_sec": "1.0",
            "dosing.micro_ml_per_sec": "1.0",
            "dosing.bloom_ml_per_sec": "1.0",
            "targets.ec_target": "0.8",
        },
    )

    # Seed only one day with dosing; backfill should still produce continuous rows.
    focus_day = date(2026, 6, 14)
    focus_start, _, _ = ndi._date_bounds(focus_day)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO dose_events(ts, pump, seconds, blocked_by) VALUES (?, ?, ?, NULL)",
            (focus_start + 3600, "grow", 5),
        )
        conn.commit()

    hist = ndi.get_ndi_history(3)
    assert [row["date"] for row in hist] == ["2026-06-12", "2026-06-13", "2026-06-14"]
    assert hist[2]["total_nutrient_ml"] == 5.0
    assert hist[0]["total_nutrient_ml"] == 0.0
    assert hist[1]["total_nutrient_ml"] == 0.0


def test_grow_history_days_uses_grow_start_date(monkeypatch, tmp_path):
    ndi, db_path = _load_module(monkeypatch, tmp_path)
    _seed_schema(db_path)

    class _FixedNow:
        def date(self):
            return date(2026, 7, 5)

    monkeypatch.setattr(ndi, "_local_now", lambda: _FixedNow())
    monkeypatch.setattr(
        ndi,
        "_read_settings",
        lambda: {
            "general.grow_start_date": "2026-06-05",
            "dosing.grow_ml_per_sec": "1.0",
            "dosing.micro_ml_per_sec": "1.0",
            "dosing.bloom_ml_per_sec": "1.0",
            "targets.ec_target": "0.8",
        },
    )

    assert ndi._grow_history_days(max_days=365, include_today=False) == 30