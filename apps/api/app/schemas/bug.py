from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "high", "medium", "low", "info", "unknown"]


class BugContract(BaseModel):
    """The 7-field bug contract used in agent JSON I/O and in the DB."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    severity: Severity
    scope_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    repro_path: str = Field(min_length=1)
    repro_usage: str = Field(min_length=1)
    missing_for_full_chain: str = Field(min_length=1)


class BugRead(BugContract):
    scope_name: str | None = None
    project_id: str | None = None


class BugCreate(BaseModel):
    """Manual bug creation via API. id is generated server-side."""
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    scope_id: str
    description: str
    repro_path: str
    repro_usage: str
    missing_for_full_chain: str = Field(min_length=1)


class BugPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity | None = None
    scope_id: str | None = None
    description: str | None = None
    repro_path: str | None = None
    repro_usage: str | None = None
    missing_for_full_chain: str | None = None


class BugListItem(BugContract):
    """Returned by /api/bugs and /api/review-queue with review metadata."""
    scope_name: str | None = None
    project_id: str | None = None
    last_reviewed_at: datetime | None = None
    last_decision: str | None = None
