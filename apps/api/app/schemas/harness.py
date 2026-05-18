from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HarnessInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    supports_resume: bool
    supports_raw_json: bool
    model_arg: str
    resume_arg: str
