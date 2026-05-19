"""Runtime configuration loaded from environment / .env (see .env.example).

Single source of truth for the DEC-007 worker limits and the DEC-008/DEC-012
security paths. Loaded once, cached as a singleton via `get_settings()`.

A malformed environment variable raises `pydantic.ValidationError` as-is —
explicit failure, no silent fallback (DEC-008 §4).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the optimAI environment (see .env.example for the keys).

    Field names are short; the prefixed env vars (MLX_*, OPTIMAI_*) are wired
    through explicit `validation_alias` declarations.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MLX inference server (DEC-017, DEC-012 loopback)
    mlx_server_url: str = Field(
        default="http://127.0.0.1:1337/v1", validation_alias="MLX_SERVER_URL"
    )
    mlx_server_port: int = Field(default=1337, validation_alias="MLX_SERVER_PORT")

    # Worker model (DEC-018)
    optimai_model: str = Field(
        default="mlx-community/Qwen2.5-Coder-32B-Instruct-4bit",
        validation_alias="OPTIMAI_MODEL",
    )

    # Worker limits (DEC-007)
    max_iterations: int = Field(default=10, ge=1, validation_alias="OPTIMAI_MAX_ITERATIONS")
    timeout_seconds: int = Field(default=300, ge=1, validation_alias="OPTIMAI_TIMEOUT_SECONDS")
    max_output_bytes: int = Field(
        default=10240, ge=1024, validation_alias="OPTIMAI_MAX_OUTPUT_BYTES"
    )

    # Security guardrails (DEC-008)
    blacklist_file: Path = Field(
        default=Path("config/blacklist.txt"), validation_alias="OPTIMAI_BLACKLIST_FILE"
    )
    sandbox_strict: bool = Field(default=True, validation_alias="OPTIMAI_SANDBOX_STRICT")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = Field(
        default="INFO", validation_alias="OPTIMAI_LOG_LEVEL"
    )
    log_file: Path = Field(default=Path("logs/optimai.log"), validation_alias="OPTIMAI_LOG_FILE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached after first call)."""
    return Settings()
