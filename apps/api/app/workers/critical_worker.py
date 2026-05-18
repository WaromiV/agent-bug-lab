from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentRun
from app.services import critical_service
from app.workers.runner import drive_run


def _apply_critical_output(s: Session, run: AgentRun, raw_output: dict[str, Any]) -> None:
    critical_service.apply_critical_output(s, run, raw_output)


async def run_critical(ctx: dict[str, Any], run_id: str) -> None:
    await drive_run(run_id, _apply_critical_output)
