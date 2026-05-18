from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    bug_bounty_url: str = Field(min_length=1)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    bug_bounty_url: str
    repo_path: str
    created_at: datetime


class ProjectCreateResponse(BaseModel):
    project: ProjectRead
    searcher_run_id: str
