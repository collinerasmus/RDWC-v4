"""
Test EC K value persistence across sensor initialization.
Ensures k value is saved to settings and restored on sensor init.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import sqlite3
from pathlib import Path


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_rdwc.db"
        yield db_path


@pytest.fixture
def mock_smbus():
    """Mock SMBus to avoid actual hardware access"""
    with patch('app.ezo_i2c_stabilized.SMBus') as mock_smbus_class:
        mock_bus = Mock()
        mock_smbus_class.return_value = mock_bus
        yield mock_smbus_class


class TestECKValuePersistence:
    """Test suite for EC K value persistence feature"""
    
    def test_k_value_validation_warns_on_non_standard(self, temp_db, mock_smbus, caplog):
        """Test that non-standard k values generate warnings but still work"""
        with patch('app.db_pool.DB_PATH', str(temp_db)):
            from app.settings import _init_settings_table, upsert_settings
            _init_settings_table()
            
            # Set non-standard k value
            upsert_settings({"ec.k_value": "5.0"})
            
            from app.ezo_i2c_stabilized import EZO, EC_ADDR
            
            ec = EZO(1, EC_ADDR, "EC")
            
            # Track commands
            commands_sent = []
            def mock_cmd(cmd, read_len=32, settle=0.3):
                commands_sent.append(cmd)
                return "OK"
            
            ec.cmd = mock_cmd
            
            # Call init_once with logging
            import logging
            with caplog.at_level(logging.WARNING):
                ec.init_once()
            
            # Verify warning was logged
            assert any("not in standard values" in record.message for record in caplog.records)
            
            # Verify K,5.00 was still sent
            assert "K,5.00" in commands_sent
    
    def test_k_value_in_settings_defaults(self):
        """Test that ec.k_value is in DEFAULTS with correct default value"""
        from app.settings import DEFAULTS
        
        assert "ec.k_value" in DEFAULTS
        # Default is now 0.1 based on K=0.1 probe standard
        assert DEFAULTS["ec.k_value"] == "0.1"
    
    def test_ec_set_k_persists_to_settings(self):
        """Test that setting k value persists to settings"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_rdwc.db"
            
            with patch('app.db_pool.DB_PATH', str(db_path)):
                # Initialize settings table
                from app.settings import _init_settings_table, upsert_settings, get_all_settings
                _init_settings_table()
                
                # Directly test the persistence logic (what the endpoint does)
                # Set k value to 0.1
                upsert_settings({"ec.k_value": "0.1"})
                
                # Verify k value was persisted
                settings = get_all_settings()
                assert settings.get("ec.k_value") == "0.1"
                
                # Update to different value
                upsert_settings({"ec.k_value": "10.0"})
                
                # Verify update worked
                settings = get_all_settings()
                assert settings.get("ec.k_value") == "10.0"
    
    def test_ec_cal_status_returns_k_from_settings(self):
        """Test that k value can be retrieved from settings (logic used by cal/status endpoint)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_rdwc.db"
            
            with patch('app.db_pool.DB_PATH', str(db_path)):
                from app.settings import _init_settings_table, upsert_settings, get_all_settings
                _init_settings_table()
                
                # Set k value to 0.1 in settings
                upsert_settings({"ec.k_value": "0.1"})
                
                # Retrieve and verify k value (what the endpoint does)
                settings = get_all_settings()
                k_value = float(settings.get("ec.k_value", "1.0"))
                
                assert k_value == 0.1
    
    def test_ezo_init_once_restores_k_value(self, temp_db, mock_smbus):
        """Test that EZO.init_once() restores k value from settings for EC sensor"""
        with patch('app.db_pool.DB_PATH', str(temp_db)):
            from app.settings import _init_settings_table, upsert_settings
            _init_settings_table()
            
            # Set k value to 0.1 in settings
            upsert_settings({"ec.k_value": "0.1"})
            
            from app.ezo_i2c_stabilized import EZO, EC_ADDR
            
            # Create EC sensor instance
            ec = EZO(1, EC_ADDR, "EC")
            
            # Track commands sent to the device
            commands_sent = []
            def mock_cmd(cmd, read_len=32, settle=0.3):
                commands_sent.append(cmd)
                return "OK"
            
            ec.cmd = mock_cmd
            
            # Call init_once
            ec.init_once()
            
            # Verify that C,0 was sent (disable continuous mode)
            assert "C,0" in commands_sent
            
            # Verify that K,0.10 was sent (restore k value with .2f formatting)
            assert "K,0.10" in commands_sent
    
    def test_non_ec_sensor_does_not_restore_k_value(self, temp_db, mock_smbus):
        """Test that non-EC sensors (pH, RTD) don't try to restore k value"""
        with patch('app.db_pool.DB_PATH', str(temp_db)):
            from app.settings import _init_settings_table, upsert_settings
            _init_settings_table()
            
            # Set k value in settings
            upsert_settings({"ec.k_value": "0.1"})
            
            from app.ezo_i2c_stabilized import EZO, PH_ADDR
            
            # Create pH sensor instance
            ph = EZO(1, PH_ADDR, "pH")
            
            # Track commands sent
            commands_sent = []
            def mock_cmd(cmd, read_len=32, settle=0.3):
                commands_sent.append(cmd)
                return "OK"
            
            ph.cmd = mock_cmd
            
            # Call init_once
            ph.init_once()
            
            # Verify that only C,0 was sent (no K command for pH)
            assert "C,0" in commands_sent
            assert not any(cmd.startswith("K,") for cmd in commands_sent)
