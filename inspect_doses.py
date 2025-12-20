#!/usr/bin/env python3
"""Inspect dose log and pH progress."""
import sqlite3
from pathlib import Path

db = Path('data/rdwc.db')
with sqlite3.connect(db) as conn:
    cur = conn.cursor()
    
    # Status counts
    cur.execute('SELECT COUNT(*), result FROM ph_dose_log GROUP BY result')
    print('=== Dose Log Summary ===')
    for count, result in cur.fetchall():
        print(f'  {result}: {count}')
    
    # Last 5 doses any type
    cur.execute('''SELECT ts_utc, result, pre_ph, post_ph, volume_ml, reason 
                   FROM ph_dose_log ORDER BY ts_utc DESC LIMIT 5''')
    print('\n=== Last 5 Doses ===')
    for ts, result, pre, post, vol, reason in cur.fetchall():
        ts_short = ts[-8:] if ts else '?'
        delta = round(post - pre, 4) if (pre and post) else 'N/A'
        reason_short = str(reason)[:30]
        print(f'  {ts_short} | {result:8} | pre={pre} post={post} ΔpH={delta} vol={vol}ml | {reason_short}')
