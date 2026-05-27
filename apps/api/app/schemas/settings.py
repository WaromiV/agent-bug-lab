from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Aligned with `claude --help`: low | medium | high | xhigh | max.
# Codex currently ignores effort; see HarnessSpec.effort_args.
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    selected_harness: str
    selected_model: str
    secondary_model: str | None
    secondary_harness: str | None
    selected_effort: Effort
    debate_max_rounds: int
    use_resume_when_available: bool
    updated_at: datetime


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_harness: str | None = None
    selected_model: str | None = None
    secondary_model: str | None = None
    secondary_harness: str | None = None
    selected_effort: Effort | None = None
    debate_max_rounds: int | None = Field(default=None, ge=1, le=20)
    use_resume_when_available: bool | None = None
