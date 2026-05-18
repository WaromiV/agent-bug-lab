from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+psycopg://agent_bug_lab:agent_bug_lab@localhost:5432/agent_bug_lab"
    redis_url: str = "redis://localhost:6379/0"

    data_dir: Path = Field(default=Path("./data"))
    fixed_repo_root: Path = Field(default=Path("/workspace/target"))

    codex_cli_bin: str = "codex"
    claude_code_cli_bin: str = "claude"
    default_harness: str = "codex"
    default_model: str = "gpt-5.5-codex"

    run_timeout_seconds: int = 7200
    searcher_min_findings: int = 1
    searcher_max_findings: int = 5
    review_stale_after_days: int = 5

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
