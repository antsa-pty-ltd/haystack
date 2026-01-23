"""Unit tests for configuration settings."""

import pytest
import os
import importlib
from unittest.mock import patch


def reload_config():
    """Helper to reload config module with fresh environment."""
    import config
    importlib.reload(config)
    return config


@pytest.fixture
def clean_env():
    """Remove all config-related env vars for clean testing."""
    env_vars = [
        "OPENAI_API_KEY", "REDIS_URL", "DATABASE_URL", "NESTJS_API_URL",
        "LOG_LEVEL", "MAX_REQUESTS_PER_USER", "SESSION_TIMEOUT_MINUTES",
        "SHOW_TOOL_BANNER", "SHOW_RAW_TOOL_JSON", "MAX_CONCURRENT_REQUESTS",
        "HOST", "PORT"
    ]
    original = {k: os.environ.get(k) for k in env_vars}
    for var in env_vars:
        os.environ.pop(var, None)
    yield
    for var, value in original.items():
        if value is not None:
            os.environ[var] = value
        else:
            os.environ.pop(var, None)


@pytest.mark.unit
class TestDefaultValues:
    """Test default configuration values."""

    def test_default_redis_url(self, clean_env):
        assert reload_config().settings.redis_url == "redis://localhost:6379"

    def test_default_nestjs_api_url(self, clean_env):
        assert reload_config().settings.nestjs_api_url == "http://localhost:8080"

    def test_default_log_level(self, clean_env):
        assert reload_config().settings.log_level == "INFO"

    def test_default_max_requests_per_user(self, clean_env):
        assert reload_config().settings.max_requests_per_user == 10

    def test_default_session_timeout(self, clean_env):
        assert reload_config().settings.session_timeout_minutes == 240

    def test_default_host(self, clean_env):
        assert reload_config().settings.host == "0.0.0.0"

    def test_default_port(self, clean_env):
        assert reload_config().settings.port == 8001


@pytest.mark.unit
class TestEnvironmentVariables:
    """Test environment variable parsing."""

    def test_redis_url_from_env(self):
        with patch.dict(os.environ, {"REDIS_URL": "redis://custom-host:6380"}):
            assert reload_config().settings.redis_url == "redis://custom-host:6380"

    def test_nestjs_api_url_from_env(self):
        with patch.dict(os.environ, {"NESTJS_API_URL": "http://api.example.com"}):
            assert reload_config().settings.nestjs_api_url == "http://api.example.com"

    def test_openai_api_key_from_env(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            assert reload_config().settings.openai_api_key == "sk-test-key"

    def test_port_from_env_as_integer(self):
        with patch.dict(os.environ, {"PORT": "9000"}):
            config = reload_config()
            assert config.settings.port == 9000
            assert isinstance(config.settings.port, int)


@pytest.mark.unit
class TestBooleanParsing:
    """Test boolean environment variable parsing."""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "Yes", "y", "Y"])
    def test_show_tool_banner_truthy_values(self, value):
        with patch.dict(os.environ, {"SHOW_TOOL_BANNER": value}):
            assert reload_config().settings.show_tool_banner is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "No", "n"])
    def test_show_tool_banner_falsy_values(self, value):
        with patch.dict(os.environ, {"SHOW_TOOL_BANNER": value}):
            assert reload_config().settings.show_tool_banner is False

    def test_show_raw_tool_json_default_false(self, clean_env):
        assert reload_config().settings.show_raw_tool_json is False

    def test_show_tool_banner_default_true(self, clean_env):
        assert reload_config().settings.show_tool_banner is True


@pytest.mark.unit
class TestIntegerParsing:
    """Test integer environment variable parsing."""

    def test_max_requests_per_user_from_env(self):
        with patch.dict(os.environ, {"MAX_REQUESTS_PER_USER": "50"}):
            config = reload_config()
            assert config.settings.max_requests_per_user == 50
            assert isinstance(config.settings.max_requests_per_user, int)

    def test_session_timeout_from_env(self):
        with patch.dict(os.environ, {"SESSION_TIMEOUT_MINUTES": "60"}):
            assert reload_config().settings.session_timeout_minutes == 60

    def test_max_concurrent_requests_from_env(self):
        with patch.dict(os.environ, {"MAX_CONCURRENT_REQUESTS": "5000"}):
            assert reload_config().settings.max_concurrent_requests == 5000


@pytest.mark.unit
class TestSettingsClass:
    """Test Settings class structure."""

    def test_is_pydantic_base_settings(self):
        from config import Settings
        from pydantic_settings import BaseSettings
        assert issubclass(Settings, BaseSettings)

    def test_has_env_file_config(self):
        from config import Settings
        assert hasattr(Settings, 'Config') or hasattr(Settings, 'model_config')

    def test_all_required_settings_exist(self):
        from config import settings
        required_attrs = [
            'openai_api_key', 'redis_url', 'database_url', 'nestjs_api_url',
            'log_level', 'max_requests_per_user', 'session_timeout_minutes',
            'show_tool_banner', 'show_raw_tool_json', 'max_concurrent_requests',
            'host', 'port'
        ]
        for attr in required_attrs:
            assert hasattr(settings, attr), f"Missing setting: {attr}"


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases in configuration."""

    def test_openai_key_is_string(self):
        from config import settings
        assert isinstance(settings.openai_api_key, str)

    def test_database_url_has_postgresql_asyncpg(self, clean_env):
        config = reload_config()
        assert "postgresql" in config.settings.database_url
        assert "asyncpg" in config.settings.database_url
