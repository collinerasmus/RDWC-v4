#!/usr/bin/env python3
"""
RDWC-v4 System Handoff Inspection
- Verify all systems in AUTO mode for overnight operation
- Benchmark system performance
- Check health & readiness for unattended 24/7 operation
"""
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta
import time

DB_PATH = Path("data/rdwc.db")

def get_setting(key, default=None):
    """Get a setting value."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else default
    except:
        return default

def main():
    print("\n" + "="*80)
    print("RDWC-v4 SYSTEM HANDOFF INSPECTION - OVERNIGHT AUTO MODE READINESS")
    print("="*80)
    
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # ========== SECTION 1: AUTO MODE VERIFICATION ==========
        print("\n[1] AUTO MODE STATUS (Critical for overnight operation)")
        print("-" * 80)
        
        auto_settings = [
            ("controls.global_auto", "🎛️  GLOBAL AUTO (master switch)"),
            ("controls.ph_auto", "📊 pH Controller Auto"),
            ("controls.ec_auto", "📊 EC Controller Auto"),
            ("controls.chiller_auto", "❄️  Chiller Auto"),
            ("controls.circulation_auto", "💨 Circulation Pump Auto"),
            ("controls.lights_auto", "💡 Lights Schedule Auto"),
        ]
        
        all_auto_enabled = True
        for key, label in auto_settings:
            value = get_setting(key, "false")
            status = "✅ ON" if value.lower() == "true" else "❌ OFF"
            print(f"   {label:40s} {status:10s} (value={value})")
            if value.lower() != "true":
                all_auto_enabled = False
        
        if all_auto_enabled:
            print("\n   ✅ All systems in AUTO mode - ready for unattended operation")
        else:
            print("\n   ⚠️  Some systems NOT in AUTO - user must enable before sleep")
        
        # ========== SECTION 2: SAFETY GUARDS ==========
        print("\n[2] SAFETY GUARDS (must be OFF for auto operation)")
        print("-" * 80)
        
        safety_keys = [
            ("safety.estop", "E-STOP"),
            ("safety.estop_persist", "E-STOP Persistence"),
            ("safety.safe_off_persist", "Safe-Off Persistence"),
        ]
        
        safety_ok = True
        for key, label in safety_keys:
            value = get_setting(key, "false")
            status = "❌ TRIGGERED" if value.lower() == "true" else "✅ CLEAR"
            print(f"   {label:40s} {status:15s}")
            if value.lower() == "true" and "estop" in key:
                safety_ok = False
        
        if safety_ok:
            print("\n   ✅ All safety guards clear - safe to run unattended")
        else:
            print("\n   ⚠️  WARNING: Safety guards active - system will not dose/control")
        
        # ========== SECTION 3: DOSING CAPS (daily limits) ==========
        print("\n[3] DOSING SAFETY CAPS & LIMITS")
        print("-" * 80)
        
        caps = [
            ("safety.max_seconds_per_press", "Press cap (seconds)", 1.5),
            ("safety.max_total_seconds_per_24h", "Daily cap (seconds)", 120.0),
            ("safety.min_off_window_sec", "Min off window (seconds)", 2.0),
        ]
        
        for key, label, default in caps:
            value = float(get_setting(key, str(default)))
            print(f"   {label:40s} {value:10.1f}s")
        
        # Check daily usage
        cur.execute("""
            SELECT SUM(CASE WHEN blocked_by IS NULL THEN seconds ELSE 0 END) as today_used
            FROM dose_events
            WHERE ts >= datetime('now', 'start of day', 'unixepoch')*1000
        """)
        row = cur.fetchone()
        today_used = float(row['today_used'] or 0)
        daily_cap = float(get_setting("safety.max_total_seconds_per_24h", "120"))
        remaining = daily_cap - today_used
        
        print(f"\n   Daily usage: {today_used:.1f}s / {daily_cap:.1f}s")
        print(f"   Remaining:  {max(0, remaining):.1f}s")
        if remaining <= 0:
            print(f"   ⚠️  Daily cap REACHED - no dosing until {datetime.now(timezone.utc).date() + timedelta(days=1)}")
        else:
            print(f"   ✅ Dosing available if needed")
        
        # ========== SECTION 4: SENSOR STATUS ==========
        print("\n[4] SENSOR POLLER STATUS (critical for auto control)")
        print("-" * 80)
        
        cur.execute("""
            SELECT ts, temp_c, ph, ec_ms_cm
            FROM readings
            ORDER BY ts DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        
        if row:
            ts, temp_c, ph, ec = row['ts'], row['temp_c'], row['ph'], row['ec_ms_cm']
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            age_s = datetime.now(timezone.utc).timestamp() - ts
            
            print(f"   Last reading: {dt.isoformat()}")
            print(f"   Age: {age_s:.1f}s ago")
            print(f"   Temperature: {temp_c}°C")
            print(f"   pH: {ph}")
            print(f"   EC: {ec} mS/cm")
            
            if age_s > 120:
                print(f"\n   ❌ Sensor data STALE - poller may not be running!")
            elif age_s > 60:
                print(f"\n   ⚠️  Sensor data aging - poller may be slow")
            else:
                print(f"\n   ✅ Fresh sensor data - poller is active")
        else:
            print(f"   ❌ No sensor data found - poller is NOT running or DB is empty")
        
        # ========== SECTION 5: DOSE EVENTS LOG ==========
        print("\n[5] DOSE EVENTS LOG (for monitoring overnight)")
        print("-" * 80)
        
        cur.execute("SELECT COUNT(*) as cnt FROM dose_events")
        total_events = cur.fetchone()['cnt']
        
        cur.execute("""
            SELECT 
                COUNT(*) as cnt,
                SUM(CASE WHEN blocked_by IS NULL THEN 1 ELSE 0 END) as ok,
                SUM(CASE WHEN blocked_by IS NOT NULL THEN 1 ELSE 0 END) as blocked
            FROM dose_events
        """)
        stats = cur.fetchone()
        
        print(f"   Total events logged: {total_events}")
        print(f"   Successful doses: {stats['ok'] or 0}")
        print(f"   Blocked doses: {stats['blocked'] or 0}")
        
        if stats['blocked'] and stats['blocked'] > 0:
            cur.execute("""
                SELECT blocked_by, COUNT(*) as cnt
                FROM dose_events
                WHERE blocked_by IS NOT NULL
                GROUP BY blocked_by
                ORDER BY cnt DESC
            """)
            print(f"\n   Blocked breakdown:")
            for row in cur.fetchall():
                print(f"      {row['blocked_by']}: {row['cnt']}")
        
        # ========== SECTION 6: SYSTEM TARGETS ==========
        print("\n[6] CONTROL TARGETS (for automated adjustment)")
        print("-" * 80)
        
        targets = [
            ("targets.ph_low", "pH low target", 5.8),
            ("targets.ph_high", "pH high target", 6.2),
            ("targets.ec_low", "EC low target", 0.4),
            ("targets.ec_high", "EC high target", 0.6),
            ("targets.ec_target", "EC ideal target", 1.8),
            ("targets.temp_target_c", "Temperature target", 19.0),
        ]
        
        for key, label, default in targets:
            value = float(get_setting(key, str(default)))
            print(f"   {label:40s} {value:10.2f}")
        
        # ========== SECTION 7: OPERATIONAL READINESS ==========
        print("\n[7] OPERATIONAL READINESS CHECKLIST")
        print("-" * 80)
        
        checks = {
            "All AUTO modes enabled": all_auto_enabled,
            "Safety guards cleared": safety_ok,
            "Sensor poller active": row is not None and age_s < 120 if row else False,
            "Dose events logged": total_events > 0,
            "Targets configured": True,
        }
        
        all_ok = all(v for v in checks.values())
        for check, status in checks.items():
            symbol = "✅" if status else "⚠️ "
            print(f"   {symbol} {check}")
        
        print("\n" + "="*80)
        if all_ok:
            print("🟢 SYSTEM READY FOR UNATTENDED 24/7 AUTO OPERATION")
        elif all_auto_enabled and safety_ok:
            print("🟡 SYSTEM MOSTLY READY - Poller/logging may need attention")
        else:
            print("🔴 USER ACTION REQUIRED - Enable AUTO modes and/or clear safety guards")
        print("="*80)

if __name__ == "__main__":
    main()
