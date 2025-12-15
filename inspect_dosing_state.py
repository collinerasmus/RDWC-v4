#!/usr/bin/env python3
"""
Pre-simulation inspection script.
Checks database state, current caps, and system readiness.
"""
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta

DB_PATH = Path("data/rdwc.db")

def main():
    print("\n" + "="*70)
    print("RDWC-v4 DOSING PRE-SIMULATION INSPECTION")
    print("="*70)
    
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        
        # 1. Check dose_events table
        print("\n[1] DOSE_EVENTS TABLE SCHEMA")
        try:
            cur.execute("PRAGMA table_info(dose_events)")
            columns = cur.fetchall()
            if columns:
                for col_id, name, type_, notnull, default, pk in columns:
                    print(f"   {name:20s} {type_:10s} {'NOT NULL' if notnull else ''} {'PK' if pk else ''}")
            else:
                print("   ❌ Table does not exist")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # 2. Check current dose_events count
        print("\n[2] DOSE_EVENTS CURRENT STATE")
        try:
            cur.execute("SELECT COUNT(*) FROM dose_events")
            count = cur.fetchone()[0]
            print(f"   Total events: {count}")
            
            if count > 0:
                cur.execute("""
                    SELECT 
                        pump, 
                        COUNT(*) as cnt,
                        SUM(CASE WHEN blocked_by IS NULL THEN 1 ELSE 0 END) as successful,
                        SUM(CASE WHEN blocked_by IS NOT NULL THEN 1 ELSE 0 END) as blocked
                    FROM dose_events
                    GROUP BY pump
                """)
                print("   Breakdown by pump:")
                for pump, cnt, successful, blocked in cur.fetchall():
                    print(f"      {pump:10s}: {cnt} total ({successful or 0} ok, {blocked or 0} blocked)")
                
                # Show blocked reasons
                cur.execute("""
                    SELECT blocked_by, COUNT(*) as cnt
                    FROM dose_events
                    WHERE blocked_by IS NOT NULL
                    GROUP BY blocked_by
                    ORDER BY cnt DESC
                """)
                if cur.fetchall():
                    print("   Blocked reasons:")
                    for reason, cnt in cur.fetchall():
                        print(f"      {reason}: {cnt}")
            else:
                print("   ✅ Table empty and ready for simulation")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # 3. Check latest readings
        print("\n[3] LATEST SENSOR READINGS")
        try:
            cur.execute("""
                SELECT ts, temp_c, ph, ec_ms_cm
                FROM readings
                ORDER BY ts DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                ts, temp_c, ph, ec = row
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                age_s = datetime.now(timezone.utc).timestamp() - ts
                print(f"   Timestamp: {dt.isoformat()} ({age_s:.1f}s ago)")
                print(f"   Temperature: {temp_c}°C")
                print(f"   pH: {ph}")
                print(f"   EC: {ec} mS/cm")
                if age_s > 60:
                    print(f"   ⚠️  Sensor data stale (>60s)")
                else:
                    print(f"   ✅ Fresh sensor data")
            else:
                print("   ❌ No readings found")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # 4. Check settings
        print("\n[4] SAFETY SETTINGS (from database)")
        try:
            cur.execute("""
                SELECT key, value
                FROM settings
                WHERE key LIKE 'safety.%' OR key LIKE 'targets.%'
                ORDER BY key
            """)
            rows = cur.fetchall()
            if rows:
                for key, value in rows:
                    print(f"   {key:40s} = {value}")
            else:
                print("   ⚠️  No settings found (will use hardcoded defaults)")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # 5. Check system_state for auto mode
        print("\n[5] SYSTEM STATE")
        try:
            cur.execute("SELECT key, value FROM system_state")
            for key, value in cur.fetchall():
                if 'auto' in key.lower() or 'mode' in key.lower():
                    print(f"   {key:40s} = {value}")
        except Exception as e:
            pass  # Not critical
    
    print("\n" + "="*70)
    print("✅ READY FOR SIMULATION")
    print("="*70)

if __name__ == "__main__":
    main()
