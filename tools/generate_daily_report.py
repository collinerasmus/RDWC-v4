#!/usr/bin/env python3
"""
RDWC Daily Grow Report Generator
Generates comprehensive HTML report with camera photo, current status, and forecasts
"""

import os
import sys
import json
import base64
import requests
from datetime import datetime, timedelta
from pathlib import Path

def fetch_json(url, timeout=10, default=None):
    """Safely fetch JSON from API"""
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ {url}: {e}", file=sys.stderr)
        return default or {}

def get_camera_snapshot(base_url):
    """Fetch camera snapshot as base64"""
    try:
        r = requests.get(f"{base_url}/camera/snapshot.jpg", timeout=10)
        r.raise_for_status()
        return base64.b64encode(r.content).decode()
    except Exception as e:
        print(f"⚠️  Camera snapshot failed: {e}", file=sys.stderr)
        return None

def generate_report(api_base_url, output_file='grow-report.html'):
    """Generate comprehensive grow report"""
    
    print(f"📊 Generating Daily Grow Report from {api_base_url}...")
    
    # Fetch all data
    settings = fetch_json(f"{api_base_url}/api/settings")
    sensors = fetch_json(f"{api_base_url}/api/sensors")
    ph_status = fetch_json(f"{api_base_url}/api/ph/status")
    ec_status = fetch_json(f"{api_base_url}/api/ec/status")
    relays = fetch_json(f"{api_base_url}/api/relays/status")
    auto_status = fetch_json(f"{api_base_url}/api/auto/status")
    schedule = fetch_json(f"{api_base_url}/api/schedule/current_week")
    temps = fetch_json(f"{api_base_url}/api/temperature/status")
    ph_trend = fetch_json(f"{api_base_url}/api/ph/trend?minutes=1440")
    ec_trend = fetch_json(f"{api_base_url}/api/trends?from={(datetime.utcnow()-timedelta(hours=24)).isoformat()}Z&to={datetime.utcnow().isoformat()}Z&gran=60&max=1500")
    
    # Get camera snapshot
    camera_b64 = get_camera_snapshot(api_base_url)
    
    # Extract settings
    general = settings.get('general', {})
    grow_name = general.get('grow_name', 'RDWC Grow')
    grow_start = general.get('grow_start_date', '')
    reservoir_liters = general.get('reservoir_liters', 'N/A')
    
    # Calculate grow age
    days_elapsed = 0
    weeks_elapsed = 0
    if grow_start:
        try:
            start = datetime.strptime(grow_start, '%Y-%m-%d')
            days_elapsed = (datetime.utcnow() - start).days
            weeks_elapsed = days_elapsed // 7
        except:
            pass
    
    # Current readings
    temp_c = sensors.get('temperature_c')
    ph_now = sensors.get('ph')
    ec_now = sensors.get('ec_mscm')
    sensor_online = sensors.get('online', False)
    age_seconds = sensors.get('age_seconds', 0)
    
    # pH targets & status
    ph_targets = ph_status.get('targets', {})
    ph_low = ph_targets.get('low', 6.0)
    ph_high = ph_targets.get('high', 6.8)
    ph_auto = ph_status.get('auto', {}).get('enabled', False)
    ph_holding = ph_status.get('auto', {}).get('holding_reason')
    ph_guards = ph_status.get('guards', {})
    today_ph_ml = ph_guards.get('today_total_ml', 0)
    
    # EC targets & status
    ec_targets = ec_status.get('targets', {})
    ec_low = ec_targets.get('low', 1.0)
    ec_high = ec_targets.get('high', 1.6)
    ec_auto = ec_status.get('auto', {}).get('enabled', False)
    ec_holding = ec_status.get('auto', {}).get('holding_reason')
    ec_today_ml = ec_status.get('guards', {}).get('today_total_ml', 0)
    
    # Get schedule for current week
    current_week = max(1, weeks_elapsed + 1)
    weeks = schedule.get('weeks', [])
    week_data = next((w for w in weeks if w['week'] == current_week), weeks[0] if weeks else {})
    
    # Trend data
    ph_trend_dir = ph_trend.get('direction', '→')
    ph_trend_str = ph_trend.get('change_str', 'stable')
    
    # System status
    relay_data = relays.get('relays', {})
    main_pump = relay_data.get('main_pump', {}).get('is_on', False)
    lights_on = relay_data.get('lights', {}).get('is_on', False)
    chiller = relay_data.get('chiller_power', {}).get('is_on', False)
    estop = relays.get('estop', False)
    mode = relays.get('mode', 'UNKNOWN').upper()
    
    # Status checks
    def check_in_range(val, low, high):
        try:
            v = float(val) if val else None
            l = float(low)
            h = float(high)
            return 'OK' if (l <= v <= h) else 'OUT OF RANGE'
        except:
            return 'N/A'
    
    ph_status_text = check_in_range(ph_now, ph_low, ph_high)
    ec_status_text = check_in_range(ec_now, ec_low, ec_high)
    temp_status_text = check_in_range(temp_c, 16, 24)
    
    # Alerts
    alerts = []
    if estop:
        alerts.append(('🚨', 'E-STOP ACTIVE', 'System is halted', 'error'))
    if not sensor_online:
        alerts.append(('⚠️', 'Sensors Offline', 'Readings may be stale', 'warning'))
    if int(age_seconds) > 300:
        alerts.append(('⚠️', 'Stale Data', f'Last reading: {age_seconds}s ago', 'warning'))
    if not main_pump:
        alerts.append(('⚠️', 'Pump Off', 'Main circulation pump is OFF', 'warning'))
    if ph_status_text == 'OUT OF RANGE':
        alerts.append(('📈', 'pH Out of Range', f'{ph_now:.2f} (target: {ph_low}-{ph_high})', 'warning'))
    if ec_status_text == 'OUT OF RANGE':
        alerts.append(('📊', 'EC Out of Range', f'{ec_now:.2f} (target: {ec_low}-{ec_high})', 'warning'))
    if not ph_auto:
        alerts.append(('💡', 'pH Auto Disabled', 'Manual dosing only', 'info'))
    if not ec_auto:
        alerts.append(('💡', 'EC Auto Disabled', 'Manual dosing only', 'info'))
    
    # Helper functions
    def fmt(v, decimals=2, suffix=''):
        if v is None: return 'N/A'
        try: return f"{float(v):.{decimals}f}{suffix}"
        except: return str(v)
    
    def status_badge(status):
        colors = {
            'OK': '#10b981',
            'OUT OF RANGE': '#ef4444',
            'N/A': '#94a3b8'
        }
        color = colors.get(status, '#94a3b8')
        return f'<span style="color:{color};font-weight:bold">{status}</span>'
    
    def alert_box(emoji, title, msg, level):
        bg_map = {'error': '#7f1d1d', 'warning': '#92400e', 'info': '#1e3a8a'}
        border_map = {'error': '#dc2626', 'warning': '#d97706', 'info': '#3b82f6'}
        bg = bg_map.get(level, '#1e293b')
        border = border_map.get(level, '#64748b')
        return f'''<div style="background:{bg};border-left:4px solid {border};padding:12px;margin:8px 0;border-radius:4px">
            <div style="font-weight:bold;margin-bottom:4px">{emoji} {title}</div>
            <div style="color:#d1d5db;font-size:13px">{msg}</div>
        </div>'''
    
    # Generate HTML
    html_parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>RDWC Daily Report - {grow_name}</title>',
        '<style>',
        'body{font-family:"Segoe UI",Tahoma,Geneva,Verdana,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:0}',
        '.wrapper{max-width:900px;margin:0 auto;padding:20px}',
        '.header{background:linear-gradient(135deg,#1e3a8a,#1e40af);border-radius:8px;padding:24px;margin-bottom:20px;border-left:6px solid #3b82f6}',
        '.header h1{margin:0 0 8px;font-size:28px;color:#e0e7ff}',
        '.header p{margin:0;color:#bfdbfe;font-size:14px}',
        '.section{background:#1e293b;border-radius:8px;padding:20px;margin-bottom:16px}',
        '.section-title{font-size:18px;font-weight:bold;color:#60a5fa;margin:0 0 16px;padding-bottom:12px;border-bottom:2px solid #334155}',
        '.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}',
        '.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}',
        '.kpi{background:#0f172a;border-radius:6px;padding:16px;border-left:4px solid #3b82f6}',
        '.kpi-label{font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}',
        '.kpi-value{font-size:32px;font-weight:bold;margin:8px 0}',
        '.kpi-target{font-size:12px;color:#94a3b8}',
        '.photo-container{border-radius:8px;overflow:hidden;background:#0f172a;padding:8px;text-align:center}',
        '.photo-container img{max-width:100%;height:auto;border-radius:4px}',
        '.status-good{color:#10b981;font-weight:bold}',
        '.status-warning{color:#f59e0b;font-weight:bold}',
        '.status-error{color:#ef4444;font-weight:bold}',
        '.badge{display:inline-block;padding:4px 12px;border-radius:4px;font-size:12px;font-weight:bold;margin:4px 4px 4px 0}',
        '.badge-on{background:#065f46;color:#6ee7b7}',
        '.badge-off{background:#450a0a;color:#fca5a5}',
        'table{width:100%;border-collapse:collapse;font-size:14px}',
        'td,th{padding:10px 8px;border-bottom:1px solid #334155;text-align:left}',
        'th{color:#64748b;font-weight:bold;background:#0f172a}',
        '.footer{text-align:center;color:#64748b;font-size:12px;padding-top:16px;margin-top:20px;border-top:1px solid #334155}',
        '</style>',
        '</head>',
        '<body>',
        '<div class="wrapper">',
        
        # Header
        '<div class="header">',
        f'<h1>{grow_name}</h1>',
        f'<p>Week {current_week} • Day {days_elapsed} • Generated {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</p>',
        '</div>',
        
        # Camera photo
        '<div class="section">',
        '<div class="section-title">🎥 Current Grow State</div>',
        '<div class="photo-container">',
    ]
    
    if camera_b64:
        html_parts.append(f'<img src="data:image/jpeg;base64,{camera_b64}" style="max-height:400px;" alt="Current grow photo">')
    else:
        html_parts.append('<div style="padding:40px;color:#64748b">📷 No camera available</div>')
    
    html_parts.extend([
        '</div>',
        '</div>',
        
        # Alerts
        '<div class="section">',
        '<div class="section-title">⚡ System Alerts</div>',
    ])
    
    if alerts:
        for emoji, title, msg, level in alerts:
            html_parts.append(alert_box(emoji, title, msg, level))
    else:
        html_parts.append('<div style="color:#10b981;padding:8px">✅ All systems normal</div>')
    
    html_parts.extend([
        '</div>',
        
        # Current status (WHERE WE ARE)
        '<div class="section">',
        '<div class="section-title">📍 Current Status - Where We Are</div>',
        '<div class="grid-3">',
        f'<div class="kpi"><div class="kpi-label">pH</div><div class="kpi-value" style="color:{["#ef4444","#10b981","#94a3b8"][["OUT OF RANGE","OK","N/A"].index(ph_status_text)]}">{fmt(ph_now)}</div><div class="kpi-target">Target: {ph_low}-{ph_high} | {ph_status_text}</div></div>',
        f'<div class="kpi"><div class="kpi-label">EC (mS/cm)</div><div class="kpi-value" style="color:{["#ef4444","#10b981","#94a3b8"][["OUT OF RANGE","OK","N/A"].index(ec_status_text)]}">{fmt(ec_now, 2)}</div><div class="kpi-target">Target: {ec_low}-{ec_high} | {ec_status_text}</div></div>',
        f'<div class="kpi"><div class="kpi-label">Water Temp (°C)</div><div class="kpi-value" style="color:{["#ef4444","#10b981","#94a3b8"][["OUT OF RANGE","OK","N/A"].index(temp_status_text)]}">{fmt(temp_c, 1)}</div><div class="kpi-target">Target: 16-24°C | {temp_status_text}</div></div>',
        '</div>',
        '<table style="margin-top:16px">',
        '<tr><td style="color:#64748b">Trend (24h)</td><td>pH: {ph_trend_dir} {ph_trend_str}</td><td>Reservoir: {reservoir_liters}L</td></tr>',
        f'<tr><td style="color:#64748b">Dosing Today</td><td>pH: {today_ph_ml:.1f}ml | Auto: <span class="status-{"good" if ph_auto else "warning"}">{["Disabled","Enabled"][int(ph_auto)]}</span></td><td>EC: {ec_today_ml:.1f}ml | Auto: <span class="status-{"good" if ec_auto else "warning"}">{["Disabled","Enabled"][int(ec_auto)]}</span></td></tr>',
        f'<tr><td style="color:#64748b">System Health</td><td>Sensors: {["OFFLINE ❌","ONLINE ✓"][int(sensor_online)]} (age: {age_seconds}s)</td><td>Mode: <strong>{mode}</strong></td></tr>',
        '</table>',
        '</div>',
        
        # Schedule & targets (WHERE WE'RE GOING)
        '<div class="section">',
        '<div class="section-title">🎯 Week {current_week} Plan - Where We\'re Going</div>',
        '<div class="grid-2">',
        f'<div><strong>Nutrient Targets</strong><br>',
        f'pH: {week_data.get("ph_low", "N/A")} - {week_data.get("ph_high", "N/A")}<br>',
        f'EC: {week_data.get("ec_target", "N/A")} mS/cm<br>',
        f'Temp: {week_data.get("temp_target", "N/A")}°C<br>',
        f'</div>',
        f'<div><strong>Per 10L Nutrients</strong><br>',
        f'Grow: {week_data.get("grow_ml10", 0)}ml<br>',
        f'Micro: {week_data.get("micro_ml10", 0)}ml<br>',
        f'Bloom: {week_data.get("bloom_ml10", 0)}ml<br>',
        f'</div>',
        '</div>',
        '<div style="margin-top:12px;padding:12px;background:#0f172a;border-left:3px solid #10b981;border-radius:4px">',
        f'<strong>Phase:</strong> {week_data.get("phase", "Unknown").title()}<br>',
        f'<strong>Lights:</strong> {week_data.get("lights", "N/A")}<br>',
        f'<strong>Notes:</strong> {week_data.get("notes", "No special notes for this week")}',
        '</div>',
        '</div>',
        
        # System relays
        '<div class="section">',
        '<div class="section-title">⚙️ Hardware Status</div>',
        '<table>',
        '<tr>',
        f'<td>Main Pump</td><td><span class="badge {"badge-on" if main_pump else "badge-off"}">{"Running" if main_pump else "Stopped"}</span></td>',
        f'<td>Lights</td><td><span class="badge {"badge-on" if lights_on else "badge-off"}">{"On" if lights_on else "Off"}</span></td>',
        '</tr>',
        '<tr>',
        f'<td>Chiller</td><td><span class="badge {"badge-on" if chiller else "badge-off"}">{"Cooling" if chiller else "Idle"}</span></td>',
        f'<td>E-Stop</td><td><span class="badge {"badge-off" if not estop else "badge-off"}">{"Clear" if not estop else "ACTIVE"}</span></td>',
        '</tr>',
        '</table>',
        '</div>',
        
        # Footer
        f'<div class="footer">🤖 RDWC-v4 Daily Report | {grow_name} | {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC</div>',
        
        '</div>',
        '</body>',
        '</html>',
    ])
    
    # Write HTML
    html = '\n'.join(html_parts)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ Report generated: {output_file}")
    print(f"   Week {current_week} | {grow_name}")
    print(f"   pH: {fmt(ph_now)} (target {ph_low}-{ph_high}) | EC: {fmt(ec_now, 2)} (target {ec_low}-{ec_high}) | Temp: {fmt(temp_c, 1)}°C")
    
    return output_file

if __name__ == '__main__':
    api_url = os.getenv('RDWC_API_URL', 'http://localhost:8080')
    output = os.getenv('REPORT_OUTPUT', 'grow-report.html')
    generate_report(api_url, output)
