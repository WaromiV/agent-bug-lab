from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["searcher_agent", "cleaner_agent", "critical_thinking_agent"]
Status = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    role: Role
    harness: str
    model: str
    status: Status
    objective: str
    resume_from_run_id: str | None
    harness_session_id: str | None
    data_dir: str
    started_at: datetime | None
    finished_at: datetime | None
    raw_input: dict[str, Any]
    raw_output: dict[str, Any] | None
    error: str | None
    created_at: datetime


class LogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    level: str
    message: str
    payload: dict[str, Any] | None
    created_at: datetime
