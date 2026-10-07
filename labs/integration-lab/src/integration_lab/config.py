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

    # Runtime
    default_max_retries: int = Field(default=3, validation_alias="DEFAULT_MAX_RETRIES")

    # Production Layer demo mode
    runner_mode: str = Field(default="test", validation_alias="RUNNER_MODE")
    demo_owner: str = Field(default="demo-owner", validation_alias="GITHUB_OWNER")
    demo_repo: str = Field(default="demo-repo", validation_alias="GITHUB_REPO")
    demo_approve_writes: bool = Field(default=False, validation_alias="DEMO_APPROVE_WRITES")


@lru_cache
def get_settings() -> Settings:
    return Settings()