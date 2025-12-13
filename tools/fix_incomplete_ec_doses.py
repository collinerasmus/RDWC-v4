#!/usr/bin/env python3
"""
Cleanup incomplete EC dose entries where post_ec is NULL.

Entries older than 24 hours are deleted.
Recent entries (<24h) attempt retroactive fix using sensor readings.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

def fix_incomplete_doses() -> None:
    """Find and fix/delete incomplete EC dose entries."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        
        # Find all entries with NULL post_ec
        cur.execute("""
            SELECT id, ts_utc, pre_ec, volume_ml, duration_ms, reason 
            FROM ec_dose_log 
            WHERE post_ec IS NULL
            ORDER BY id ASC
        """)
        
        incomplete = cur.fetchall()
        
        if not incomplete:
            print("No incomplete dose entries found")
            return
        
        print(f"Found {len(incomplete)} incomplete dose entries")
        
        fixed_count = 0
        deleted_count = 0
        
        for rowid, ts_utc, pre_ec, volume_ml, duration_ms, reason in incomplete:
            dose_time = datetime.fromisoformat(ts_utc.replace('Z', '+00:00'))
            age_hours = (datetime.now(timezone.utc) - dose_time).total_seconds() / 3600
            
            # Delete entries older than 24 hours (unlikely to have useful data)
            if age_hours > 24:
                cur.execute("DELETE FROM ec_dose_log WHERE id=?", (rowid,))
                deleted_count += 1
                print(f"  Deleted old incomplete entry: id={rowid}, ts={ts_utc}, age={age_hours:.1f}h")
                continue
            
            # Try to find an EC reading shortly after the dose (within 10 minutes)
            after_time = (dose_time + timedelta(minutes=10)).isoformat()
            cur.execute("""
                SELECT ec_mscm FROM readings 
                WHERE ts > ? AND ts <= ? AND ec_mscm IS NOT NULL 
                ORDER BY ts ASC 
                LIMIT 1
            """, (ts_utc, after_time))
            
            row = cur.fetchone()
            if row:
                post_ec = row[0]
                # Update with retroactive EC reading and add flag to reason
                new_reason = f"{reason or 'dose'} [retroactive_fix]" if reason else "dose [retroactive_fix]"
                cur.execute("""
                    UPDATE ec_dose_log 
                    SET post_ec=?, reason=? 
                    WHERE id=?
                """, (post_ec, new_reason, rowid))
                fixed_count += 1
                print(f"  Fixed: id={rowid}, ts={ts_utc}, post_ec={post_ec:.3f}")
            else:
                # No post reading available - delete the entry
                cur.execute("DELETE FROM ec_dose_log WHERE id=?", (rowid,))
                deleted_count += 1
                print(f"  Deleted (no post reading): id={rowid}, ts={ts_utc}")
        
        conn.commit()
        
        print(f"\n✓ Cleanup complete: {fixed_count} fixed, {deleted_count} deleted")

if __name__ == "__main__":
    fix_incomplete_doses()
