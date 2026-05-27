from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    bug_bounty_url: str = Field(min_length=1)
    repo_path: str | None = Field(default=None, description="Override the default fixed_repo_root for this project")


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    bug_bounty_url: str
    repo_path: str
    prepare_dossier: dict | None = None
    prepare_run_id: str | None = None
    static_facts: dict | None = None
    static_facts_generated_at: datetime | None = None
    created_at: datetime


class ProjectCreateResponse(BaseModel):
    project: ProjectRead
    prepare_run_id: str
