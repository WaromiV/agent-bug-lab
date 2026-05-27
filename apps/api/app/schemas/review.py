from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewerRole = Literal["cleaner_agent", "human"]
Decision = Literal["kept", "removed", "refined", "needs_more_work"]


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bug_id: str
    project_id: str
    run_id: str | None
    reviewer_role: ReviewerRole
    decision: Decision
    notes: str
    created_at: datetime


class CleanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bug_ids: list[str] = Field(min_length=1)


