"""
Background monitoring for RDWC-v4 system
Continuously checks sensors and triggers alerts based on thresholds
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import sqlite3
from pathlib import Path

from .config import cfg
from .alerts import (
    alert_ph_out_of_range, 
    alert_ec_out_of_range, 
    alert_temp_out_of_range,
    alert_sensor_offline
)

# Import from src/rdwc since this is the main module structure
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))
from rdwc.sensors import Sensors

logger = logging.getLogger(__name__)

# Global monitoring state
_monitoring_active = False
_monitor_task: Optional[asyncio.Task] = None
_sensor_failure_counts: Dict[str, int] = {}


class MonitoringState:
    """Track alert states with hysteresis"""
    def __init__(self):
        self.ph_alert_active = False
        self.ec_alert_active = False
        self.temp_alert_active = False
        self.last_good_reading = datetime.now()
        self.grace_period_start: Optional[datetime] = None


_state = MonitoringState()


def _safe_float(v):
    """Safely convert value to float, returning None for empty/invalid values"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def get_latest_sensor_data() -> Optional[Dict[str, Any]]:
    """Get latest sensor readings from database"""
    try:
        db_path = Path("data/rdwc.db")
        if not db_path.exists():
            logger.warning("Database file not found")
            return None
        
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get most recent reading from correct table
            cursor.execute("""
                SELECT ts, temp_c, ph, ec_ms_cm FROM readings 
                ORDER BY ts DESC 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if row:
                # Map to expected format with safe parsing
                return {
                    'timestamp': row['ts'],
                    'water_temp': _safe_float(row['temp_c']),
                    'ph': _safe_float(row['ph']),
                    'ec': _safe_float(row['ec_ms_cm'])
                }
            return None
            
    except Exception as e:
        logger.error(f"Failed to read sensor data from DB: {e}")
        return None


async def check_sensor_thresholds() -> None:
    """Check sensor values against thresholds and trigger alerts"""
    config = cfg()
    
    # Try to get latest data from database first
    sensor_data = get_latest_sensor_data()
    
    # If no recent DB data, try reading sensors directly
    if not sensor_data:
        try:
            sensors = Sensors()
            sensor_data = sensors.sample_once()
        except Exception as e:
            logger.error(f"Failed to read sensors directly: {e}")
            await alert_sensor_offline("All sensors")
            return
    
    if not sensor_data:
        logger.warning("No sensor data available")
        return
    
    # Update last good reading time
    _state.last_good_reading = datetime.now()
    
    # Extract sensor values
    ph = sensor_data.get('ph')
    ec = sensor_data.get('ec') 
    temp = sensor_data.get('water_temp')
    
    # Check pH with hysteresis
    if ph is not None:
        ph_low_threshold = config.ph_low + (config.ph_hyst if _state.ph_alert_active else 0)
        ph_high_threshold = config.ph_high - (config.ph_hyst if _state.ph_alert_active else 0)
        
        if ph < config.ph_low and not _state.ph_alert_active:
            _state.ph_alert_active = True
            await alert_ph_out_of_range(ph, False)
        elif ph > config.ph_high and not _state.ph_alert_active:
            _state.ph_alert_active = True
            await alert_ph_out_of_range(ph, True)
        elif ph_low_threshold <= ph <= ph_high_threshold and _state.ph_alert_active:
            # pH back in range - start grace period
            if _state.grace_period_start is None:
                _state.grace_period_start = datetime.now()
            elif datetime.now() - _state.grace_period_start >= timedelta(minutes=config.alert_recovery_grace_min):
                _state.ph_alert_active = False
                _state.grace_period_start = None
                logger.info("pH alert cleared after grace period")
    
    # Check EC with hysteresis
    if ec is not None:
        ec_low_threshold = config.ec_low + (config.ec_hyst if _state.ec_alert_active else 0)
        ec_high_threshold = config.ec_high - (config.ec_hyst if _state.ec_alert_active else 0)
        
        if ec < config.ec_low and not _state.ec_alert_active:
            _state.ec_alert_active = True
            await alert_ec_out_of_range(ec, False)
        elif ec > config.ec_high and not _state.ec_alert_active:
            _state.ec_alert_active = True
            await alert_ec_out_of_range(ec, True)
        elif ec_low_threshold <= ec <= ec_high_threshold and _state.ec_alert_active:
            if _state.grace_period_start is None:
                _state.grace_period_start = datetime.now()
            elif datetime.now() - _state.grace_period_start >= timedelta(minutes=config.alert_recovery_grace_min):
                _state.ec_alert_active = False
                _state.grace_period_start = None
                logger.info("EC alert cleared after grace period")
    
    # Check temperature with hysteresis
    if temp is not None:
        temp_low_threshold = config.temp_low + (config.temp_hyst if _state.temp_alert_active else 0)
        temp_high_threshold = config.temp_high - (config.temp_hyst if _state.temp_alert_active else 0)
        
        if temp < config.temp_low and not _state.temp_alert_active:
            _state.temp_alert_active = True
            await alert_temp_out_of_range(temp, False)
        elif temp > config.temp_high and not _state.temp_alert_active:
            _state.temp_alert_active = True
            await alert_temp_out_of_range(temp, True)
        elif temp_low_threshold <= temp <= temp_high_threshold and _state.temp_alert_active:
            if _state.grace_period_start is None:
                _state.grace_period_start = datetime.now()
            elif datetime.now() - _state.grace_period_start >= timedelta(minutes=config.alert_recovery_grace_min):
                _state.temp_alert_active = False
                _state.grace_period_start = None
                logger.info("Temperature alert cleared after grace period")


async def monitoring_loop() -> None:
    """Main monitoring loop"""
    logger.info("Starting sensor monitoring loop")
    
    while _monitoring_active:
        try:
            await check_sensor_thresholds()
            
            # Check for stale sensor data
            time_since_reading = datetime.now() - _state.last_good_reading
            if time_since_reading > timedelta(minutes=10):  # No readings for 10+ minutes
                await alert_sensor_offline("Sensor data stale")
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
        
        # Wait for next check (configurable interval)
        await asyncio.sleep(60)  # Check every minute
    
    logger.info("Monitoring loop stopped")


def start_monitoring() -> bool:
    """Start background monitoring task"""
    global _monitoring_active, _monitor_task
    
    if _monitoring_active:
        logger.warning("Monitoring already active")
        return False
    
    _monitoring_active = True
    _monitor_task = asyncio.create_task(monitoring_loop())
    logger.info("Background monitoring started")
    return True


def stop_monitoring() -> bool:
    """Stop background monitoring task"""
    global _monitoring_active, _monitor_task
    
    if not _monitoring_active:
        logger.warning("Monitoring not active")
        return False
    
    _monitoring_active = False
    
    if _monitor_task:
        _monitor_task.cancel()
        _monitor_task = None
    
    logger.info("Background monitoring stopped")
    return True


def get_monitoring_status() -> Dict[str, Any]:
    """Get current monitoring status"""
    return {
        "active": _monitoring_active,
        "last_good_reading": _state.last_good_reading.isoformat(),
        "active_alerts": {
            "ph": _state.ph_alert_active,
            "ec": _state.ec_alert_active,
            "temperature": _state.temp_alert_active
        },
        "grace_period_active": _state.grace_period_start is not None,
        "sensor_failure_counts": _sensor_failure_counts.copy()
    }


def reset_alert_states() -> None:
    """Reset all alert states - useful for testing"""
    global _state
    _state = MonitoringState()
    _sensor_failure_counts.clear()
    logger.info("Alert states reset")