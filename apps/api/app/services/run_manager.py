from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import next_id
from app.core.logging import get_logger
from app.core.paths import run_dir, write_json
from app.db.models import AgentLog, AgentRun

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def create_run(
    db: Session,
    *,
    project_id: str,
    role: str,
    harness: str,
    model: str,
    objective: str,
    raw_input: dict[str, Any],
    resume_from_run_id: str | None = None,
    harness_session_id: str | None = None,
    run_id: str | None = None,
) -> AgentRun:
    """Insert a queued run row and pre-create its data directory."""
    rid = run_id or next_id(db, "run")
    identifier = _run_identifier(role, rid, raw_input)
    data_dir = run_dir(role, identifier)
    run = AgentRun(
        id=rid,
        project_id=project_id,
        role=role,
        harness=harness,
        model=model,
        status="queued",
        objective=objective,
        resume_from_run_id=resume_from_run_id,
        harness_session_id=harness_session_id,
        data_dir=str(data_dir),
        raw_input=raw_input,
    )
    db.add(run)
    db.flush()
    log.info(
        "run.queued",
        run_id=run.id,
        project_id=project_id,
        role=role,
        harness=harness,
        model=model,
        data_dir=run.data_dir,
    )
    return run


def _run_identifier(role: str, run_id: str, raw_input: dict[str, Any]) -> str:
    """Cleaner runs use the review_id; everything else uses the run_id."""
    if role == "cleaner_agent":
        review_id = raw_input.get("task_id") or run_id
        return review_id
    return run_id


def mark_running(db: Session, run: AgentRun) -> None:
    run.status = "running"
    run.started_at = _now()
    db.flush()
    log.info("run.started", run_id=run.id, role=run.role, project_id=run.project_id)


def mark_succeeded(db: Session, run: AgentRun, raw_output: dict[str, Any]) -> None:
    run.status = "succeeded"
    run.raw_output = raw_output
    run.finished_at = _now()
    if isinstance(raw_output, dict):
        session_id = raw_output.get("harness_session_id")
        if isinstance(session_id, str):
            run.harness_session_id = session_id
    db.flush()
    log.info("run.succeeded", run_id=run.id, role=run.role, project_id=run.project_id)


def mark_failed(db: Session, run: AgentRun, error: str, raw_output: dict[str, Any] | None = None) -> None:
    run.status = "failed"
    run.error = error
    run.raw_output = raw_output
    run.finished_at = _now()
    db.flush()
    log.warning(
        "run.failed",
        run_id=run.id,
        role=run.role,
        project_id=run.project_id,
        error=error,
    )


def mark_cancelled(db: Session, run: AgentRun) -> None:
    run.status = "cancelled"
    run.finished_at = _now()
    db.flush()
    log.info("run.cancelled", run_id=run.id, role=run.role, project_id=run.project_id)


def append_log(
    db: Session,
    run_id: str,
    level: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(AgentLog(run_id=run_id, level=level, message=message, payload=payload))
    db.flush()


def list_runs(db: Session, *, project_id: str | None = None, limit: int = 200) -> list[AgentRun]:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(AgentRun.project_id == project_id)
    return list(db.execute(stmt).scalars())


def list_logs(db: Session, run_id: str, *, after_id: int | None = None, limit: int = 500) -> list[AgentLog]:
    stmt = select(AgentLog).where(AgentLog.run_id == run_id).order_by(AgentLog.id.asc()).limit(limit)
    if after_id is not None:
        stmt = stmt.where(AgentLog.id > after_id)
    return list(db.execute(stmt).scalars())


def data_dir_for(run: AgentRun) -> Path:
    return Path(run.data_dir)


def write_ingest_report(run: AgentRun, payload: dict[str, Any]) -> None:
    write_json(data_dir_for(run) / "ingest_report.json", payload)
