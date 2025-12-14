#!/usr/bin/env python3
"""
Seed lights event data from Dec 1 to today.
Simulates 16h ON, 8h OFF schedule (lights_on_time: 15:00, lights_duration_hours: 16)
"""
import sys
import os
from datetime import datetime, timedelta
import json

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.relays_core import _relay_event_logs

def seed_lights_events():
    """Generate lights events from Dec 1 to today."""
    start_date = datetime(2025, 12, 1, 0, 0, 0)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    lights_on_time = "15:00"  # 3 PM
    lights_duration_hours = 16  # 16h ON, 8h OFF
    
    on_h, on_m = map(int, lights_on_time.split(':'))
    
    current_date = start_date
    event_count = 0
    
    while current_date <= today:
        # Lights ON at 15:00
        on_datetime = current_date.replace(hour=on_h, minute=on_m, second=0)
        event_on = {
            "ts": on_datetime.isoformat(),
            "requested": False,
            "final": True,  # ON
            "reason": "schedule",
            "cooldown": 0,
            "blocked": False,
            "caller": "scheduler:edge"
        }
        _relay_event_logs["lights"].append(event_on)
        event_count += 1
        
        # Lights OFF 16h later
        off_datetime = on_datetime + timedelta(hours=lights_duration_hours)
        event_off = {
            "ts": off_datetime.isoformat(),
            "requested": False,
            "final": False,  # OFF
            "reason": "schedule",
            "cooldown": 0,
            "blocked": False,
            "caller": "scheduler:edge"
        }
        _relay_event_logs["lights"].append(event_off)
        event_count += 1
        
        current_date += timedelta(days=1)
    
    return event_count

if __name__ == "__main__":
    try:
        count = seed_lights_events()
        # Get events to verify
        events = list(_relay_event_logs.get("lights", []))
        print(f"✓ Seeded {count} events")
        print(f"✓ Total events in memory: {len(events)}")
        if events:
            print(f"  First: {events[0]['ts']} ({events[0]['final']=})")
            print(f"  Last:  {events[-1]['ts']} ({events[-1]['final']=})")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
