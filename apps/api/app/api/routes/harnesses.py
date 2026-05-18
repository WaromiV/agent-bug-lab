from __future__ import annotations

from fastapi import APIRouter

from app.schemas.harness import HarnessInfo
from app.services.harness_runner import list_harnesses

router = APIRouter(prefix="/harnesses", tags=["harnesses"])


@router.get("", response_model=list[HarnessInfo])
def list_harnesses_endpoint() -> list[HarnessInfo]:
    return [
        HarnessInfo(
            name=h.name,
            supports_resume=h.supports_resume,
            supports_raw_json=h.supports_raw_json,
            model_arg=h.model_arg,
            resume_arg=h.resume_arg,
        )
        for h in list_harnesses()
    ]
