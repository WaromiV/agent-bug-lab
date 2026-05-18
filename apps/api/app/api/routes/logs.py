from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.api.deps import DbSession
from app.db.models import AgentLog
from app.schemas.run import LogRead

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[LogRead])
def list_logs(
    db: DbSession,
    run_id: str | None = Query(default=None),
    limit: int = Query(default=500, le=2000),
) -> list[LogRead]:
    stmt = select(AgentLog).order_by(desc(AgentLog.id)).limit(limit)
    if run_id:
        stmt = stmt.where(AgentLog.run_id == run_id)
    return [LogRead.model_validate(log) for log in db.execute(stmt).scalars()]
