"""
Test EC calibration for K=0.1 probes.
Tests the new dry calibration and updated calibration values.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app import sensor_controller


@pytest.fixture
def mock_i2c_available():
    """Mock I2C availability."""
    with patch.object(sensor_controller, '_I2C_AVAILABLE', True):
        yield


@pytest.fixture
def mock_settings():
    """Mock settings with K=0.1."""
    return {
        "ec.k_value": "0.1"
    }


@pytest.fixture
def mock_ezo_device():
    """Mock EZO device."""
    mock_dev = Mock()
    mock_dev.cmd = Mock(return_value="OK")
    mock_dev.calibration_cmd = Mock(return_value=True)  # Calibration commands return True on success
    mock_dev.close = Mock()
    mock_dev.init_once = Mock()
    return mock_dev


def test_default_k_value_is_01():
    """Test that default K value is 0.1 for K=0.1 probes."""
    from app.settings import DEFAULTS
    assert DEFAULTS.get("ec.k_value") == "0.1"


def test_calibrate_ec_dry_default_value(mock_i2c_available, mock_settings, mock_ezo_device):
    """Test dry calibration endpoint exists and uses correct command."""
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=mock_settings), \
         patch('app.settings.upsert_settings', return_value=None), \
         patch('app.sensor_controller._acquire_calib_lock', return_value=True), \
         patch('app.sensor_controller._release_calib_lock'):
        
        result = sensor_controller.calibrate_ec_dry()
        
        assert result["ok"] is True
        # Verify Cal,dry command was sent via calibration_cmd
        calls = [str(call) for call in mock_ezo_device.calibration_cmd.call_args_list]
        assert any("Cal,dry" in str(call) for call in calls)
        # Verify K was restored
        calls = [str(call) for call in mock_ezo_device.cmd.call_args_list]
        assert any("K,0.1" in str(call) or "K,0.10" in str(call) for call in calls)


def test_calibrate_ec_low_default_is_84(mock_i2c_available, mock_settings, mock_ezo_device):
    """Test low point calibration uses 84 µS/cm for K=0.1 probes."""
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=mock_settings), \
         patch('app.settings.upsert_settings', return_value=None), \
         patch('app.sensor_controller._acquire_calib_lock', return_value=True), \
         patch('app.sensor_controller._release_calib_lock'):
        
        # Call without argument should use default 84
        result = sensor_controller.calibrate_ec_low()
        
        assert result["ok"] is True
        # Verify Cal,low,84 command was sent via calibration_cmd
        calls = [str(call) for call in mock_ezo_device.calibration_cmd.call_args_list]
        assert any("Cal,low,84" in str(call) for call in calls)


def test_calibrate_ec_high_default_is_1413(mock_i2c_available, mock_settings, mock_ezo_device):
    """Test high point calibration uses 1413 µS/cm for K=0.1 probes (standard two-point)."""
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=mock_settings), \
         patch('app.settings.upsert_settings', return_value=None), \
         patch('app.sensor_controller._acquire_calib_lock', return_value=True), \
         patch('app.sensor_controller._release_calib_lock'):
        
        # Call without argument should use default 1413 for K=0.1
        result = sensor_controller.calibrate_ec_high()
        
        assert result["ok"] is True
        # Verify Cal,high,1413 command was sent via calibration_cmd
        calls = [str(call) for call in mock_ezo_device.calibration_cmd.call_args_list]
        assert any("Cal,high,1413" in str(call) for call in calls)


def test_calibrate_ec_low_custom_value(mock_i2c_available, mock_settings, mock_ezo_device):
    """Test low point calibration accepts custom value."""
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=mock_settings), \
         patch('app.settings.upsert_settings', return_value=None), \
         patch('app.sensor_controller._acquire_calib_lock', return_value=True), \
         patch('app.sensor_controller._release_calib_lock'):
        
        # Call with custom value
        result = sensor_controller.calibrate_ec_low(us_cm=1413)
        
        assert result["ok"] is True
        # Verify Cal,low,1413 command was sent via calibration_cmd
        calls = [str(call) for call in mock_ezo_device.calibration_cmd.call_args_list]
        assert any("Cal,low,1413" in str(call) for call in calls)


def test_get_ec_calibration_status_parses_dry(mock_i2c_available, mock_ezo_device):
    """Test calibration status correctly reads from database."""
    # Update settings to include dry calibration
    settings_with_dry = {
        "ec.k_value": "0.1",
        "ec.cal_dry": "1",
        "ec.cal_low_us": "0",
        "ec.cal_high_us": "0"
    }
    # Mock response from probe
    mock_ezo_device.cmd = Mock(return_value="?CAL,1")
    
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=settings_with_dry):
        
        result = sensor_controller.get_ec_calibration_status()
        
        assert result["ok"] is True
        assert result["k"] == 0.1
        assert result["dry"] is True
        assert result["low"] is False
        assert result["high"] is False
        assert "dry" in result["cal"].lower()


def test_get_ec_calibration_status_parses_one_point(mock_i2c_available, mock_ezo_device):
    """Test calibration status correctly reads one-point from database."""
    # Update settings to include low calibration
    settings_with_low = {
        "ec.k_value": "0.1",
        "ec.cal_dry": "0",
        "ec.cal_low_us": "84",
        "ec.cal_high_us": "0"
    }
    # Mock response from probe
    mock_ezo_device.cmd = Mock(return_value="?CAL,1")
    
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=settings_with_low):
        
        result = sensor_controller.get_ec_calibration_status()
        
        assert result["ok"] is True
        assert result["dry"] is False
        assert result["low"] is True
        assert result["high"] is False
        assert result["low_us"] == 84
        assert "one-point" in result["cal"].lower() or "low" in result["cal"].lower()


def test_get_ec_calibration_status_parses_uncalibrated(mock_i2c_available, mock_ezo_device):
    """Test calibration status correctly reads uncalibrated from database."""
    # Settings with no calibration
    settings_uncal = {
        "ec.k_value": "0.1",
        "ec.cal_dry": "0",
        "ec.cal_low_us": "0",
        "ec.cal_high_us": "0"
    }
    # Mock response from probe
    mock_ezo_device.cmd = Mock(return_value="?CAL,0")
    
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=settings_uncal):
        
        result = sensor_controller.get_ec_calibration_status()
        
        assert result["ok"] is True
        assert result["dry"] is False
        assert result["low"] is False
        assert result["high"] is False
        assert result["cal"] == "uncalibrated"


def test_calibration_sequence_restores_k_value(mock_i2c_available, mock_settings, mock_ezo_device):
    """Test that K value is restored after each calibration step."""
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=mock_settings), \
         patch('app.settings.upsert_settings', return_value=None), \
         patch('app.sensor_controller._acquire_calib_lock', return_value=True), \
         patch('app.sensor_controller._release_calib_lock'):
        
        # Dry calibration
        mock_ezo_device.cmd.reset_mock()
        mock_ezo_device.calibration_cmd.reset_mock()
        result = sensor_controller.calibrate_ec_dry()
        assert result["ok"] is True
        calls = [str(call) for call in mock_ezo_device.cmd.call_args_list]
        assert any("K,0.1" in str(call) or "K,0.10" in str(call) for call in calls)
        
        # Low calibration
        mock_ezo_device.cmd.reset_mock()
        mock_ezo_device.calibration_cmd.reset_mock()
        result = sensor_controller.calibrate_ec_low()
        assert result["ok"] is True
        calls = [str(call) for call in mock_ezo_device.cmd.call_args_list]
        assert any("K,0.1" in str(call) or "K,0.10" in str(call) for call in calls)
        
        # High calibration
        mock_ezo_device.cmd.reset_mock()
        mock_ezo_device.calibration_cmd.reset_mock()
        result = sensor_controller.calibrate_ec_high()
        assert result["ok"] is True
        calls = [str(call) for call in mock_ezo_device.cmd.call_args_list]
        assert any("K,0.1" in str(call) or "K,0.10" in str(call) for call in calls)


def test_calibration_requires_lock(mock_i2c_available, mock_settings, mock_ezo_device):
    """Test that calibration requires acquiring lock."""
    with patch('app.sensor_controller.ezo_i2c_stabilized.EZO', return_value=mock_ezo_device), \
         patch('app.settings.get_all_settings', return_value=mock_settings), \
         patch('app.settings.upsert_settings', return_value=None), \
         patch('app.sensor_controller._acquire_calib_lock', return_value=False):
        
        # Dry calibration should fail without lock
        result = sensor_controller.calibrate_ec_dry()
        assert result["ok"] is False
        assert "lock" in result["error"].lower()
        
        # Low calibration should fail without lock
        result = sensor_controller.calibrate_ec_low()
        assert result["ok"] is False
        assert "lock" in result["error"].lower()
        
        # High calibration should fail without lock
        result = sensor_controller.calibrate_ec_high()
        assert result["ok"] is False
        assert "lock" in result["error"].lower()
