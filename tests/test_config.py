"""Tests for optimai.config — Settings loading and the get_settings singleton."""

import pytest
from pydantic import ValidationError

from optimai.config import Settings, get_settings

# Prefixed env vars the test environment must not leak into Settings().
_ENV_KEYS = (
    "MLX_SERVER_URL",
    "MLX_SERVER_PORT",
    "OPTIMAI_MODEL",
    "OPTIMAI_MAX_ITERATIONS",
    "OPTIMAI_TIMEOUT_SECONDS",
    "OPTIMAI_MAX_OUTPUT_BYTES",
    "OPTIMAI_BLACKLIST_FILE",
    "OPTIMAI_SANDBOX_STRICT",
    "OPTIMAI_LOG_LEVEL",
    "OPTIMAI_LOG_FILE",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove any prefixed env vars so the .env file alone drives Settings."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_minimal_env_applies_defaults(tmp_path, clean_env):
    env_file = tmp_path / ".env"
    env_file.write_text("OPTIMAI_MAX_ITERATIONS=4\n", encoding="utf-8")

    settings = Settings(_env_file=str(env_file))

    # Provided value wins.
    assert settings.max_iterations == 4
    # Everything else falls back to the documented defaults.
    assert settings.timeout_seconds == 300
    assert settings.max_output_bytes == 10240
    assert settings.mlx_server_url == "http://127.0.0.1:1337/v1"
    assert settings.optimai_model == "mlx-community/Qwen2.5-Coder-32B-Instruct-4bit"
    assert settings.sandbox_strict is True
    assert settings.log_level == "INFO"


def test_invalid_value_raises(tmp_path, clean_env):
    env_file = tmp_path / ".env"
    env_file.write_text("OPTIMAI_MAX_ITERATIONS=0\n", encoding="utf-8")

    # max_iterations has ge=1 — 0 must fail explicitly (DEC-008 §4).
    with pytest.raises(ValidationError):
        Settings(_env_file=str(env_file))


def test_sandbox_strict_false_parses_as_bool(tmp_path, clean_env):
    env_file = tmp_path / ".env"
    env_file.write_text("OPTIMAI_SANDBOX_STRICT=false\n", encoding="utf-8")

    settings = Settings(_env_file=str(env_file))

    assert settings.sandbox_strict is False


def test_bad_log_level_rejected(tmp_path, clean_env):
    env_file = tmp_path / ".env"
    env_file.write_text("OPTIMAI_LOG_LEVEL=TRACE\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        Settings(_env_file=str(env_file))


def test_get_settings_is_a_singleton():
    assert get_settings() is get_settings()
