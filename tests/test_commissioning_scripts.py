"""Tests for commissioning scripts.

Tests use mocked HTTP responses for offline testing.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add tools directory to path
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from commission_utils import (
    APIClient, APIError, create_report, save_report,
    print_status, wait_for_stability, prompt_user
)


class TestAPIClient:
    """Test API client functionality."""
    
    @patch('commission_utils.requests.Session')
    def test_api_client_init(self, mock_session):
        """Test API client initialization."""
        client = APIClient(base_url="http://test:8080", timeout=15)
        assert client.base_url == "http://test:8080"
        assert client.timeout == 15
        assert mock_session.called
    
    @patch('commission_utils.requests.Session')
    def test_api_client_get_success(self, mock_session):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance
        
        client = APIClient()
        response = client.get("/test")
        
        assert response.json() == {"status": "ok"}
    
    @patch('commission_utils.requests.Session')
    def test_api_client_get_error(self, mock_session):
        """Test GET request error handling."""
        import requests
        
        mock_session_instance = Mock()
        mock_session_instance.get.side_effect = requests.exceptions.RequestException("Connection error")
        mock_session.return_value = mock_session_instance
        
        client = APIClient()
        
        with pytest.raises(APIError):
            client.get("/test")
    
    @patch('commission_utils.requests.Session')
    def test_api_client_post_success(self, mock_session):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        
        mock_session_instance = Mock()
        mock_session_instance.post.return_value = mock_response
        mock_session.return_value = mock_session_instance
        
        client = APIClient()
        response = client.post("/test", json_data={"key": "value"})
        
        assert response.json() == {"ok": True}


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_create_report(self):
        """Test report creation with all fields."""
        report = create_report(
            script_name="test_script.py",
            version="1.0.0",
            config={"key": "value"},
            results={"test": "pass"},
            errors=["error1"],
            recommendations=["rec1"]
        )
        
        assert report["metadata"]["script"] == "test_script.py"
        assert report["metadata"]["version"] == "1.0.0"
        assert "timestamp" in report["metadata"]
        assert "host" in report["metadata"]
        assert report["config"] == {"key": "value"}
        assert report["results"] == {"test": "pass"}
        assert report["errors"] == ["error1"]
        assert report["recommendations"] == ["rec1"]
    
    def test_save_report(self, tmp_path):
        """Test saving report to file."""
        report = {
            "metadata": {"script": "test"},
            "results": {"status": "ok"}
        }
        
        output_file = tmp_path / "test_report.json"
        save_report(report, str(output_file))
        
        assert output_file.exists()
        
        with open(output_file, 'r') as f:
            loaded = json.load(f)
        
        assert loaded == report
    
    def test_print_status(self, capsys):
        """Test status printing."""
        print_status("Test message", "info", use_color=False)
        captured = capsys.readouterr()
        assert "[INFO]" in captured.out
        assert "Test message" in captured.out
    
    def test_prompt_user_auto_advance(self, capsys):
        """Test user prompt with auto-advance."""
        result = prompt_user("Continue?", auto_advance=True)
        captured = capsys.readouterr()
        assert result is True
        assert "auto-advance" in captured.out
    
    @patch('builtins.input', return_value='y')
    def test_prompt_user_yes(self, mock_input):
        """Test user prompt with yes response."""
        result = prompt_user("Continue?", auto_advance=False)
        assert result is True
    
    @patch('builtins.input', return_value='n')
    def test_prompt_user_no(self, mock_input):
        """Test user prompt with no response."""
        result = prompt_user("Continue?", auto_advance=False)
        assert result is False


class TestWaitForStability:
    """Test wait_for_stability function."""
    
    @patch('commission_utils.time.sleep')
    @patch('commission_utils.APIClient')
    def test_stability_achieved(self, mock_client_class, mock_sleep):
        """Test successful stability achievement."""
        mock_client = Mock()
        mock_response = Mock()
        
        # Return stable values
        mock_response.json.side_effect = [
            {"value": 7.00},
            {"value": 7.01},
            {"value": 7.00},
        ]
        mock_client.get.return_value = mock_response
        
        success, final_value, readings = wait_for_stability(
            client=mock_client,
            read_endpoint="/test",
            value_key="value",
            threshold=0.05,
            timeout_s=30,
            check_interval=1,
            use_color=False
        )
        
        assert success is True
        assert final_value is not None
        assert len(readings) >= 3
    
    @patch('commission_utils.time.sleep')
    @patch('commission_utils.time.time')
    @patch('commission_utils.APIClient')
    def test_stability_timeout(self, mock_client_class, mock_time, mock_sleep):
        """Test timeout when stability not achieved."""
        mock_client = Mock()
        mock_response = Mock()
        
        # Return unstable values
        mock_response.json.side_effect = [
            {"value": 7.00},
            {"value": 7.50},
            {"value": 6.50},
        ]
        mock_client.get.return_value = mock_response
        
        # Mock time to simulate timeout
        mock_time.side_effect = [0, 5, 10, 50]  # Last call exceeds timeout
        
        success, final_value, readings = wait_for_stability(
            client=mock_client,
            read_endpoint="/test",
            value_key="value",
            threshold=0.05,
            timeout_s=30,
            check_interval=1,
            use_color=False
        )
        
        assert success is False


class TestSensorCommissioning:
    """Test sensor commissioning script logic."""
    
    @patch('os.path.exists')
    def test_i2c_device_check(self, mock_exists):
        """Test I2C device existence check."""
        # Import here to avoid module-level execution
        import commission_sensors
        
        mock_exists.return_value = True
        result = commission_sensors.check_i2c_device("/dev/i2c-1")
        assert result is True
        
        mock_exists.return_value = False
        result = commission_sensors.check_i2c_device("/dev/i2c-1")
        assert result is False


class TestPHCommissioning:
    """Test pH commissioning script logic."""
    
    @patch('commission_utils.APIClient')
    def test_check_capabilities_success(self, mock_client_class):
        """Test pH calibration capabilities check."""
        import commission_ph
        
        mock_client = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"caps": ["mid", "low", "high"]}
        mock_client.get.return_value = mock_response
        
        result = commission_ph.check_capabilities(mock_client)
        
        assert result["success"] is True
        assert "capabilities" in result


class TestECCommissioning:
    """Test EC commissioning script logic."""
    
    @patch('commission_utils.APIClient')
    def test_set_k_value_success(self, mock_client_class):
        """Test EC K-value setting."""
        import commission_ec
        
        mock_client = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_client.post.return_value = mock_response
        
        result = commission_ec.set_k_value(mock_client, 1.0)
        
        assert result["success"] is True
        assert result["k_value"] == 1.0


class TestRelayCommissioning:
    """Test relay commissioning script logic."""
    
    @patch('commission_utils.APIClient')
    def test_get_relay_status(self, mock_client_class):
        """Test getting relay status."""
        import commission_relays
        
        mock_client = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {
            "mode": "auto",
            "estop": False,
            "relays": {}
        }
        mock_client.get.return_value = mock_response
        
        result = commission_relays.get_relay_status(mock_client)
        
        assert result["mode"] == "auto"
        assert result["estop"] is False


class TestPumpCommissioning:
    """Test pump commissioning script logic."""
    
    @patch('commission_utils.APIClient')
    def test_discover_pumps_success(self, mock_client_class):
        """Test pump discovery."""
        import commission_pumps
        
        mock_client = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {
            "pumps": {
                "ph_up": {"relay": "dosing_ph_up", "ml_per_sec": 0.0},
                "grow": {"relay": "dosing_grow", "ml_per_sec": 0.0},
            }
        }
        mock_client.get.return_value = mock_response
        
        result = commission_pumps.discover_pumps(mock_client)
        
        assert result["success"] is True
        assert len(result["pumps"]) == 2


class TestJSONOutput:
    """Test JSON output schemas."""
    
    def test_sensor_report_schema(self):
        """Test sensor report has expected structure."""
        report = create_report(
            script_name="commission_sensors.py",
            version="1.0.0",
            config={},
            results={
                "i2c_device": {"exists": True},
                "sensor_addresses": {"success": True},
            },
            errors=[],
            recommendations=[]
        )
        
        # Validate expected fields
        assert "metadata" in report
        assert "config" in report
        assert "results" in report
        assert "errors" in report
        assert "recommendations" in report
        
        # Validate metadata
        assert report["metadata"]["script"] == "commission_sensors.py"
        assert "timestamp" in report["metadata"]
    
    def test_exit_codes(self):
        """Test that scripts define correct exit codes."""
        import commission_sensors
        import commission_ph
        import commission_ec
        import commission_relays
        import commission_pumps
        
        # Each script should have defined exit codes in docstring
        assert "Exit Codes:" in commission_sensors.__doc__
        assert "Exit Codes:" in commission_ph.__doc__
        assert "Exit Codes:" in commission_ec.__doc__
        assert "Exit Codes:" in commission_relays.__doc__
        assert "Exit Codes:" in commission_pumps.__doc__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
