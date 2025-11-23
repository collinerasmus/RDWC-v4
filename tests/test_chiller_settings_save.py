"""
Test chiller settings save functionality to ensure proper handling of all fields.
This test validates that the /api/settings endpoint properly handles chiller settings
including hysteresis and stage fields.
"""
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    """Create a test client with isolated database."""
    from app import settings
    from app.main import app
    
    # Create temporary database
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    
    # Save original DB path and seeded flag
    original = settings.DB_PATH
    original_seeded = settings._defaults_seeded
    settings.DB_PATH = tmp_path
    # Reset the seeded flag to ensure table initialization for temporary DB
    settings._defaults_seeded = False
    
    # Initialize database table
    settings._ensure_table_seed_defaults()
    
    # Initialize settings with defaults
    settings.upsert_settings({
        'chiller.target_temp': '19.0',
        'chiller.hysteresis': '0.5',
        'chiller.stage': 'default',
        'targets.temp_target_c': '19.0',
        'alerts.temp_lo_alert': '16.0',
        'alerts.temp_hi_alert': '24.0',
        'safety.chiller_min_off_s': '300',
        'safety.chiller_min_on_s': '60'
    })
    
    yield TestClient(app)
    
    # Cleanup
    settings.DB_PATH = original
    settings._defaults_seeded = original_seeded
    try:
        os.unlink(tmp_path)
    except Exception:
        pass


def test_chiller_settings_save_all_fields(client):
    """Test that all chiller settings fields can be saved and retrieved."""
    # Prepare updates matching what controller_settings.js sends
    updates = {
        'targets.temp_target_c': '20.0',
        'chiller.target_temp': '20.0',
        'chiller.hysteresis': '0.7',
        'chiller.stage': 'veg',
        'alerts.temp_lo_alert': '17.0',
        'alerts.temp_hi_alert': '23.0',
        'safety.chiller_min_off_s': '400',
        'safety.chiller_min_on_s': '80'
    }
    
    # Save settings
    response = client.put('/api/settings', json=updates)
    assert response.status_code == 200, f"Save failed: {response.text}"
    
    data = response.json()
    assert data['ok'] is True
    assert 'updated' in data
    
    # Retrieve settings to verify they were saved
    response = client.get('/api/settings')
    assert response.status_code == 200
    
    settings = response.json()
    
    # Verify all fields were saved correctly
    assert settings['targets']['temp_target_c'] == '20.0'
    assert settings['chiller']['target_temp'] == '20.0'
    assert settings['chiller']['hysteresis'] == '0.7'
    assert settings['chiller']['stage'] == 'veg'
    assert settings['alerts']['temp_lo_alert'] == '17.0'
    assert settings['alerts']['temp_hi_alert'] == '23.0'
    assert settings['safety']['chiller_min_off_s'] == '400'
    assert settings['safety']['chiller_min_on_s'] == '80'


def test_chiller_status_includes_stage(client):
    """Test that chiller status API returns the stage field."""
    # Set a stage
    client.put('/api/settings', json={'chiller.stage': 'flower'})
    
    # Get chiller status
    response = client.get('/api/chiller/status')
    assert response.status_code == 200
    
    data = response.json()
    assert 'stage' in data, "Stage field missing from chiller status"
    assert data['stage'] == 'flower'


def test_chiller_settings_api_endpoint(client):
    """Test the dedicated /api/chiller/settings endpoint."""
    # Use the chiller-specific settings endpoint
    updates = {
        'target_temp': 21.0,
        'hysteresis': 0.8,
        'stage': 'flower'
    }
    
    response = client.post('/api/chiller/settings', json=updates)
    assert response.status_code == 200, f"Chiller settings save failed: {response.text}"
    
    data = response.json()
    assert data['ok'] is True
    
    # Verify settings were saved by checking chiller status
    response = client.get('/api/chiller/status')
    assert response.status_code == 200
    
    status = response.json()
    assert status['target_temp'] == 21.0
    assert status['hysteresis'] == 0.8
    assert status['stage'] == 'flower'


def test_partial_chiller_settings_update(client):
    """Test that partial updates work correctly (only updating some fields)."""
    # First, set initial values
    client.put('/api/settings', json={
        'chiller.hysteresis': '0.5',
        'chiller.stage': 'default'
    })
    
    # Update only hysteresis
    response = client.put('/api/settings', json={'chiller.hysteresis': '0.9'})
    assert response.status_code == 200
    
    # Verify hysteresis changed but stage remained
    response = client.get('/api/settings')
    settings = response.json()
    assert settings['chiller']['hysteresis'] == '0.9'
    assert settings['chiller']['stage'] == 'default'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
