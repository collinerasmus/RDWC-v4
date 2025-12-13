#!/usr/bin/env python3
"""One-time cleanup script to fix incomplete pH dose log entries.

Finds entries where post_ph is NULL and either:
1. Deletes them if they're very old (>24 hours) and never completed
2. Updates them with the nearest pH reading after the dose timestamp

Run this once to clean up historical incomplete entries.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"


def fix_incomplete_doses():
    """Fix or delete incomplete pH dose entries."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        
        # Find incomplete entries (post_ph is NULL)
        cur.execute("""
            SELECT id, ts_utc, pre_ph 
            FROM ph_dose_log 
            WHERE post_ph IS NULL 
            ORDER BY id DESC
        """)
        incomplete = cur.fetchall()
        
        if not incomplete:
            print("✓ No incomplete dose entries found")
            return
        
        print(f"Found {len(incomplete)} incomplete dose entries")
        
        fixed = 0
        deleted = 0
        
        for rowid, ts_utc, pre_ph in incomplete:
            dose_time = datetime.fromisoformat(ts_utc.replace('Z', '+00:00'))
            age_hours = (datetime.now(dose_time.tzinfo) - dose_time).total_seconds() / 3600
            
            # If older than 24 hours and still incomplete, delete it
            if age_hours > 24:
                cur.execute("DELETE FROM ph_dose_log WHERE id=?", (rowid,))
                deleted += 1
                print(f"  Deleted old incomplete entry: id={rowid}, ts={ts_utc}, age={age_hours:.1f}h")
                continue
            
            # Try to find a pH reading shortly after the dose (within 10 minutes)
            after_time = (dose_time + timedelta(minutes=10)).isoformat()
            cur.execute("""
                SELECT ph FROM readings 
                WHERE ts > ? AND ts <= ? AND ph IS NOT NULL 
                ORDER BY ts ASC 
                LIMIT 1
            """, (ts_utc, after_time))
            
            row = cur.fetchone()
            if row:
                post_ph = row[0]
                cur.execute("""
                    UPDATE ph_dose_log 
                    SET post_ph=?, reason=COALESCE(reason, '') || '; retroactive_fix' 
                    WHERE id=?
                """, (post_ph, rowid))
                fixed += 1
                print(f"  Fixed entry: id={rowid}, ts={ts_utc}, post_ph={post_ph:.3f}")
            else:
                # No reading available; delete the entry
                cur.execute("DELETE FROM ph_dose_log WHERE id=?", (rowid,))
                deleted += 1
                print(f"  Deleted (no post reading): id={rowid}, ts={ts_utc}")
        
        conn.commit()
        
        print(f"\n✓ Cleanup complete: {fixed} fixed, {deleted} deleted")


if __name__ == "__main__":
    fix_incomplete_doses()
