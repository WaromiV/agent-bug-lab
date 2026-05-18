from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bug


def export_bugs(db: Session, *, project_id: str | None = None, bug_ids: list[str] | None = None) -> list[dict[str, Any]]:
    q = select(Bug)
    if project_id:
        q = q.where(Bug.scope_id == project_id)
    if bug_ids:
        q = q.where(Bug.id.in_(bug_ids))
    return [
        {
            "id": b.id,
            "severity": b.severity,
            "scope_id": b.scope_id,
            "description": b.description,
            "repro_path": b.repro_path,
            "repro_usage": b.repro_usage,
            "missing_for_full_chain": b.missing_for_full_chain,
        }
        for b in db.execute(q).scalars()
    ]
