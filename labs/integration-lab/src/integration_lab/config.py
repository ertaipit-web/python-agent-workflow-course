from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service
    service_name: str = "agent-course-capstone"
    service_host: str = "0.0.0.0"
    service_port: int = 8000
    log_level: str = "INFO"

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/agent_course",
        validation_alias="DATABASE_URL",
    )

    # GitHub API
    github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")
    github_base_url: str = Field(default="https://api.github.com", validation_alias="GITHUB_BASE_URL")

    # Model Provider (Week 4)
    model_provider: str = Field(default="ollama", validation_alias="MODEL_PROVIDER")
    model_name: str = Field(default="qwen3:8b", validation_alias="MODEL_NAME")
    model_base_url: str = Field(default="http://localhost:11434/v1", validation_alias="MODEL_BASE_URL")
    model_api_key: str = Field(default="", validation_alias="MODEL_API_KEY")

    # Runtime
    max_concurrent_tasks: int = 3
    task_timeout_seconds: int = 300
    default_max_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()