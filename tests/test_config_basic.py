"""
Basic tests for config module focusing on parsers and environment handling.
"""


def test_parse_bool_true_variants():
    """_parse_bool should recognize multiple true values."""
    from app.config import _parse_bool
    
    assert _parse_bool("true") is True
    assert _parse_bool("True") is True
    assert _parse_bool("1") is True
    assert _parse_bool("yes") is True
    assert _parse_bool("on") is True


def test_parse_bool_false_variants():
    """_parse_bool should return False for unrecognized values."""
    from app.config import _parse_bool
    
    assert _parse_bool("false") is False
    assert _parse_bool("0") is False
    assert _parse_bool("no") is False
    assert _parse_bool("") is False


def test_parse_bool_default():
    """_parse_bool should use default for None."""
    from app.config import _parse_bool
    
    assert _parse_bool(None, default=False) is False
    assert _parse_bool(None, default=True) is True


def test_parse_recipients_empty():
    """_parse_recipients should return empty list for empty string."""
    from app.config import _parse_recipients
    
    assert _parse_recipients("") == []


def test_parse_recipients_single():
    """_parse_recipients should parse single email."""
    from app.config import _parse_recipients
    
    result = _parse_recipients("user@example.com")
    assert result == ["user@example.com"]


def test_parse_recipients_multiple():
    """_parse_recipients should parse comma-separated emails."""
    from app.config import _parse_recipients
    
    result = _parse_recipients("user1@example.com, user2@example.com, user3@example.com")
    assert len(result) == 3
    assert "user1@example.com" in result
    assert "user2@example.com" in result
    assert "user3@example.com" in result


def test_parse_recipients_whitespace():
    """_parse_recipients should strip whitespace from emails."""
    from app.config import _parse_recipients
    
    result = _parse_recipients("  user1@example.com  ,  user2@example.com  ")
    assert result == ["user1@example.com", "user2@example.com"]


def test_pinmap_contains_expected_keys():
    """PINMAP should contain all expected relay names."""
    from app.config import PINMAP
    
    expected = ["ph_up", "grow_pump", "micro_pump", "bloom_pump", 
                "main_pump", "chiller_pump", "water_chiller", "grow_lights"]
    for key in expected:
        assert key in PINMAP
        assert isinstance(PINMAP[key], int)


def test_cfg_returns_config_instance():
    """cfg() should return a Config dataclass instance."""
    from app.config import cfg, Config
    
    config = cfg()
    assert isinstance(config, Config)


def test_cfg_frozen():
    """Config dataclass should be frozen (immutable)."""
    from app.config import cfg
    
    config = cfg()
    try:
        config.ph_low = 9.9  # type: ignore
        assert False, "Expected AttributeError for frozen dataclass"
    except AttributeError:
        pass  # Expected


def test_cfg_defaults(monkeypatch):
    """cfg() should use sensible defaults when env vars not set."""
    from app.config import cfg
    
    # Clear relevant env vars
    for key in ["PH_LOW", "PH_HIGH", "EC_LOW", "TEMP_LOW"]:
        monkeypatch.delenv(key, raising=False)
    
    config = cfg()
    
    # Check defaults from code
    assert config.ph_low == 5.5
    assert config.ph_high == 6.3
    assert config.ec_low == 1.2
    assert config.temp_low == 18.0


def test_cfg_respects_env_override(monkeypatch):
    """cfg() should respect environment variable overrides."""
    from app.config import cfg
    
    monkeypatch.setenv("PH_LOW", "5.8")
    monkeypatch.setenv("PH_HIGH", "6.5")
    
    config = cfg()
    
    assert config.ph_low == 5.8
    assert config.ph_high == 6.5
