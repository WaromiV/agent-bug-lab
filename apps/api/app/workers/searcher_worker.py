from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AgentRun
from app.services import bug_ingest, run_manager
from app.workers.runner import drive_run


def _apply_searcher_output(s: Session, run: AgentRun, raw_output: dict[str, Any]) -> None:
    cfg = get_settings()
    bugs = bug_ingest.validate_and_ingest(
        s,
        run,
        raw_output,
        min_findings=cfg.searcher_min_findings,
        max_findings=cfg.searcher_max_findings,
    )
    run_manager.write_ingest_report(
        run,
        {
            "inserted_bug_ids": [b.id for b in bugs],
            "count": len(bugs),
            "harness_session_id": raw_output.get("harness_session_id"),
        },
    )


async def run_searcher(ctx: dict[str, Any], run_id: str) -> None:
    await drive_run(run_id, _apply_searcher_output)
