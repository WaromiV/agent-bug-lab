from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    selected_harness: str
    selected_model: str
    use_resume_when_available: bool
    updated_at: datetime


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_harness: str | None = None
    selected_model: str | None = None
    use_resume_when_available: bool | None = None
