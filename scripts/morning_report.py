#!/usr/bin/env python3
"""
RDWC Morning Report Generator
Creates daily report with sensor readings and system status
Enhanced with alert system integration and 24-hour statistics
"""

import os
import json
import urllib.request
import urllib.error
import sqlite3
import statistics
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPORT_DIR = "/home/pi/reports"
API_BASE = "http://127.0.0.1:8080"
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# Add app path for imports
sys.path.append(str(Path(__file__).parent.parent / "app"))

def ensure_report_dir():
    """Ensure report directory exists"""
    os.makedirs(REPORT_DIR, exist_ok=True)

def fetch_api_data(endpoint):
    """Fetch data from API endpoint"""
    try:
        url = f"{API_BASE}/{endpoint}"
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {"error": str(e)}


def get_24h_stats():
    """Get 24-hour sensor statistics from database"""
    if not DB_PATH.exists():
        return None
    
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get readings from last 24 hours
            since_ts = datetime.now() - timedelta(hours=24)
            cursor.execute("""
                SELECT ph, ec, water_temp, timestamp 
                FROM sensor_data 
                WHERE timestamp >= ?
                ORDER BY timestamp
            """, (since_ts.isoformat(),))
            
            rows = cursor.fetchall()
            if not rows:
                return None
            
            # Extract values
            ph_values = [row['ph'] for row in rows if row['ph'] is not None]
            ec_values = [row['ec'] for row in rows if row['ec'] is not None]
            temp_values = [row['water_temp'] for row in rows if row['water_temp'] is not None]
            
            if not (ph_values and ec_values and temp_values):
                return None
            
            return {
                'readings_count': len(rows),
                'ph': {
                    'min': min(ph_values),
                    'max': max(ph_values),
                    'avg': statistics.mean(ph_values),
                    'samples': len(ph_values)
                },
                'ec': {
                    'min': min(ec_values),
                    'max': max(ec_values), 
                    'avg': statistics.mean(ec_values),
                    'samples': len(ec_values)
                },
                'temperature': {
                    'min': min(temp_values),
                    'max': max(temp_values),
                    'avg': statistics.mean(temp_values),
                    'samples': len(temp_values)
                }
            }
            
    except Exception as e:
        print(f"Error getting 24h stats: {e}")
        return None


async def send_alert_report(report_content):
    """Send report via alert system"""
    try:
        from alerts import send_alert
        return await send_alert("morning_report", report_content)
    except Exception as e:
        print(f"Error sending alert: {e}")
        return False

def generate_report():
    """Generate daily morning report"""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    report_file = os.path.join(REPORT_DIR, f"rdwc_report_{date_str}.txt")
    
    # Fetch current data
    status = fetch_api_data("status")
    relay_status = fetch_api_data("relay/status")
    schedule = fetch_api_data("schedule")
    
    # Generate report content
    report_lines = [
        f"RDWC-v4 Morning Report - {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
    ]
    
    if "error" in status:
        report_lines.extend([
            "⚠️  API UNAVAILABLE",
            f"Error: {status['error']}",
            f"Timestamp: {now.isoformat()}",
            "",
            "System may need attention - check service status.",
            ""
        ])
    else:
        # Sensor readings
        temp = status.get("temp_c", "N/A")
        ph = status.get("ph", "N/A")
        ec = status.get("ec_ms_cm", "N/A")
        age = status.get("age_s", "N/A")
        
        report_lines.extend([
            "📊 CURRENT READINGS:",
            f"   Temperature: {temp}°C",
            f"   pH Level:    {ph}",
            f"   EC:          {ec} mS/cm",
            f"   Data Age:    {age}s",
            "",
        ])
        
        # Add 24-hour statistics
        stats = get_24h_stats()
        if stats:
            report_lines.extend([
                "📈 24-HOUR STATISTICS:",
                f"   Total Readings: {stats['readings_count']}",
                "",
                f"   pH Range:     {stats['ph']['min']:.2f} - {stats['ph']['max']:.2f}",
                f"   pH Average:   {stats['ph']['avg']:.2f}",
                "",
                f"   EC Range:     {stats['ec']['min']:.2f} - {stats['ec']['max']:.2f} mS/cm",
                f"   EC Average:   {stats['ec']['avg']:.2f} mS/cm",
                "",
                f"   Temp Range:   {stats['temperature']['min']:.1f} - {stats['temperature']['max']:.1f}°C",
                f"   Temp Average: {stats['temperature']['avg']:.1f}°C",
                "",
            ])
        else:
            report_lines.extend([
                "📈 24-HOUR STATISTICS:",
                "   No historical data available",
                "",
            ])
        
        # Relay status
        if "error" not in relay_status:
            report_lines.extend([
                "🔌 RELAY STATUS:",
                f"   Main Pump:     {'ON' if relay_status.get('main_pump') else 'OFF'}",
                f"   Chiller Pump:  {'ON' if relay_status.get('chiller_pump') else 'OFF'}",
                f"   Water Chiller: {'ON' if relay_status.get('water_chiller') else 'OFF'}",
                f"   Grow Lights:   {'ON' if relay_status.get('grow_lights') else 'OFF'}",
                f"   Micro Pump:    {'ON' if relay_status.get('micro_pump') else 'OFF'}",
                f"   Grow Pump:     {'ON' if relay_status.get('grow_pump') else 'OFF'}",
                f"   Bloom Pump:    {'ON' if relay_status.get('bloom_pump') else 'OFF'}",
                f"   pH Up:         {'ON' if relay_status.get('ph_up') else 'OFF'}",
                "",
            ])
        
        # Scheduler status
        if "error" not in schedule:
            sched_enabled = schedule.get("enabled", False)
            entry_count = len(schedule.get("entries", []))
            report_lines.extend([
                "⏰ SCHEDULER:",
                f"   Status:    {'ENABLED' if sched_enabled else 'DISABLED'}",
                f"   Entries:   {entry_count} scheduled tasks",
                "",
            ])
    
    # Write report
    try:
        with open(report_file, 'w') as f:
            f.write('\n'.join(report_lines))
        print(f"Report generated: {report_file}")
        return 0
    except Exception as e:
        print(f"Error writing report: {e}")
        return 1

async def main():
    """Main function with optional alert sending"""
    ensure_report_dir()
    
    # Generate file report
    result = generate_report()
    
    # Check if we should send alerts (via command line flag)
    send_alerts = len(sys.argv) > 1 and sys.argv[1] == "--send-alerts"
    
    if send_alerts:
        print("Sending morning report via alerts...")
        try:
            # Generate report content for alerts (simpler format)
            status = fetch_api_data("status")
            alert_content = f"""🌅 RDWC Morning Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}

Current Status:
• pH: {status.get('ph', 'N/A')}
• EC: {status.get('ec_ms_cm', 'N/A')} mS/cm  
• Temperature: {status.get('temp_c', 'N/A')}°C

"""
            stats = get_24h_stats()
            if stats:
                alert_content += f"""24h Averages:
• pH: {stats['ph']['avg']:.2f} (range: {stats['ph']['min']:.2f}-{stats['ph']['max']:.2f})
• EC: {stats['ec']['avg']:.2f} mS/cm (range: {stats['ec']['min']:.2f}-{stats['ec']['max']:.2f})
• Temp: {stats['temperature']['avg']:.1f}°C (range: {stats['temperature']['min']:.1f}-{stats['temperature']['max']:.1f})

Total readings: {stats['readings_count']}"""
            else:
                alert_content += "24h Statistics: No data available"
            
            success = await send_alert_report(alert_content)
            if success:
                print("Alert sent successfully")
            else:
                print("Failed to send alert")
                
        except Exception as e:
            print(f"Error sending alert: {e}")
    
    return result


if __name__ == "__main__":
    import sys
    result = asyncio.run(main())
    sys.exit(result)