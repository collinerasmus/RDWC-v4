"""
Alert system for RDWC-v4 - Telegram and Email notifications
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, Any
import httpx
import logging
from datetime import datetime, timedelta
from .config import cfg

logger = logging.getLogger(__name__)

# Global debounce tracking
_last_alert_times: Dict[str, datetime] = {}


def should_send_alert(alert_key: str) -> bool:
    """Check if enough time has passed since last alert of this type"""
    config = cfg()
    now = datetime.now()
    
    if alert_key not in _last_alert_times:
        _last_alert_times[alert_key] = now
        return True
    
    time_since_last = now - _last_alert_times[alert_key]
    if time_since_last >= timedelta(minutes=config.alert_debounce_min):
        _last_alert_times[alert_key] = now
        return True
    
    return False


async def send_telegram(message: str, alert_key: str = "general") -> bool:
    """Send Telegram message with debouncing"""
    config = cfg()
    
    if not config.alert_enable_telegram:
        logger.debug("Telegram alerts disabled")
        return False
    
    if not config.telegram_bot_token or not config.telegram_chat_id:
        logger.warning("Telegram credentials not configured")
        return False
    
    if not should_send_alert(f"telegram_{alert_key}"):
        logger.debug(f"Telegram alert '{alert_key}' debounced")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": config.telegram_chat_id,
            "text": f"🚨 RDWC Alert: {message}",
            "parse_mode": "Markdown"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Telegram alert sent: {alert_key}")
                return True
            else:
                logger.error(f"Telegram API error {response.status_code}: {response.text}")
                return False
                    
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


async def send_email(subject: str, message: str, alert_key: str = "general") -> bool:
    """Send email alert with debouncing"""
    config = cfg()
    
    if not config.alert_enable_email:
        logger.debug("Email alerts disabled")
        return False
    
    if not config.smtp_host or not config.alert_recipients:
        logger.warning("Email not configured (missing SMTP host or recipients)")
        return False
    
    if not should_send_alert(f"email_{alert_key}"):
        logger.debug(f"Email alert '{alert_key}' debounced")
        return False
    
    try:
        # Create email
        msg = MIMEMultipart()
        msg['From'] = config.smtp_user or "rdwc@localhost"
        msg['To'] = ", ".join(config.alert_recipients)
        msg['Subject'] = f"RDWC Alert: {subject}"
        
        # Email body
        body = f"""
RDWC-v4 System Alert
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{message}

---
This alert was generated automatically by the RDWC monitoring system.
"""
        msg.attach(MIMEText(body, 'plain'))
        
        # Send via SMTP
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            if config.smtp_user and config.smtp_pass:
                server.starttls()
                server.login(config.smtp_user, config.smtp_pass)
            
            server.sendmail(msg['From'], config.alert_recipients, msg.as_string())
        
        logger.info(f"Email alert sent: {alert_key}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


async def send_alert(alert_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> bool:
    """Send alert via all enabled channels"""
    config = cfg()
    
    # Format enhanced message with data
    if data:
        enhanced_msg = f"{message}\n\nSensor Data:\n"
        for key, value in data.items():
            if isinstance(value, float):
                enhanced_msg += f"• {key.replace('_', ' ').title()}: {value:.2f}\n"
            else:
                enhanced_msg += f"• {key.replace('_', ' ').title()}: {value}\n"
    else:
        enhanced_msg = message
    
    # Send to both channels
    telegram_success = False
    email_success = False
    
    if config.alert_enable_telegram:
        telegram_success = await send_telegram(enhanced_msg, alert_type)
    
    if config.alert_enable_email:
        email_success = await send_email(alert_type.replace('_', ' ').title(), enhanced_msg, alert_type)
    
    return telegram_success or email_success


# Convenience functions for common alert types
async def alert_ph_out_of_range(ph_value: float, is_high: bool) -> bool:
    """Alert for pH out of range"""
    config = cfg()
    direction = "HIGH" if is_high else "LOW"
    range_str = f"{config.ph_low:.1f}-{config.ph_high:.1f}"
    
    message = f"pH {direction}: {ph_value:.2f} (target: {range_str})"
    data = {"ph_current": ph_value, "ph_target_range": range_str}
    
    return await send_alert("ph_alert", message, data)


async def alert_ec_out_of_range(ec_value: float, is_high: bool) -> bool:
    """Alert for EC out of range"""
    config = cfg()
    direction = "HIGH" if is_high else "LOW"
    range_str = f"{config.ec_low:.1f}-{config.ec_high:.1f}"
    
    message = f"EC {direction}: {ec_value:.2f} mS/cm (target: {range_str})"
    data = {"ec_current": ec_value, "ec_target_range": range_str}
    
    return await send_alert("ec_alert", message, data)


async def alert_temp_out_of_range(temp_value: float, is_high: bool) -> bool:
    """Alert for temperature out of range"""
    config = cfg()
    direction = "HIGH" if is_high else "LOW"
    range_str = f"{config.temp_low:.1f}-{config.temp_high:.1f}"
    
    message = f"Temperature {direction}: {temp_value:.1f}°C (target: {range_str})"
    data = {"temperature_current": temp_value, "temp_target_range": range_str}
    
    return await send_alert("temp_alert", message, data)


async def alert_pump_failure(pump_name: str) -> bool:
    """Alert for pump/system failure"""
    message = f"System failure detected: {pump_name}"
    data = {"failed_component": pump_name, "timestamp": datetime.now().isoformat()}
    
    return await send_alert("system_failure", message, data)


async def alert_sensor_offline(sensor_name: str) -> bool:
    """Alert for sensor connectivity issues"""
    message = f"Sensor offline or unresponsive: {sensor_name}"
    data = {"offline_sensor": sensor_name, "timestamp": datetime.now().isoformat()}
    
    return await send_alert("sensor_offline", message, data)


async def test_alerts() -> Dict[str, bool]:
    """Test all alert channels - useful for setup verification"""
    results = {}
    
    # Test Telegram
    if cfg().alert_enable_telegram:
        results['telegram'] = await send_telegram("Test message from RDWC system", "test")
    
    # Test Email  
    if cfg().alert_enable_email:
        results['email'] = await send_email("Test Alert", "This is a test message from RDWC system", "test")
    
    return results