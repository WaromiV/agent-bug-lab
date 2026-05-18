from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentRun
from app.services import cleaner_service
from app.workers.runner import drive_run


def _apply_cleaner_output(s: Session, run: AgentRun, raw_output: dict[str, Any]) -> None:
    cleaner_service.apply_cleaner_output(s, run, raw_output)


async def run_cleaner(ctx: dict[str, Any], run_id: str) -> None:
    await drive_run(run_id, _apply_cleaner_output)
