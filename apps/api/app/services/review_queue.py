from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import next_id
from app.core.logging import get_logger
from app.db.models import Bug, BugReview, Scope

log = get_logger(__name__)


def _latest_review_per_bug(db: Session, bug_ids: list[str]) -> dict[str, BugReview]:
    if not bug_ids:
        return {}
    stmt = (
        select(BugReview)
        .where(BugReview.bug_id.in_(bug_ids))
        .order_by(BugReview.bug_id, desc(BugReview.created_at))
    )
    out: dict[str, BugReview] = {}
    for r in db.execute(stmt).scalars():
        out.setdefault(r.bug_id, r)
    return out


def list_review_queue(db: Session, *, project_id: str | None = None) -> list[dict[str, Any]]:
    """Bugs with no review OR latest review older than REVIEW_STALE_AFTER_DAYS."""
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().review_stale_after_days)

    latest = (
        select(BugReview.bug_id, func.max(BugReview.created_at).label("last_reviewed_at"))
        .group_by(BugReview.bug_id)
        .subquery()
    )
    q = (
        select(Bug, latest.c.last_reviewed_at)
        .outerjoin(latest, latest.c.bug_id == Bug.id)
    )
    if project_id:
        scope_ids = [s for (s,) in db.execute(
            select(Scope.id).where(Scope.project_id == project_id)
        ).all()]
        q = q.where(Bug.scope_id.in_(scope_ids))
    q = q.where((latest.c.last_reviewed_at.is_(None)) | (latest.c.last_reviewed_at <= cutoff))

    rows = db.execute(q).all()
    log.info(
        "review_queue.calculated",
        project_id=project_id,
        count=len(rows),
        stale_cutoff=cutoff.isoformat(),
    )

    bug_ids = [b.id for b, _ in rows]
    latest_decisions = _latest_review_per_bug(db, bug_ids)

    scope_meta = {
        s.id: (s.name, s.project_id)
        for s in db.query(Scope).filter(Scope.id.in_({b.scope_id for b, _ in rows})).all()
    }
    return [
        {
            "id": b.id,
            "severity": b.severity,
            "scope_id": b.scope_id,
            "scope_name": scope_meta.get(b.scope_id, (None, None))[0],
            "project_id": scope_meta.get(b.scope_id, (None, None))[1],
            "description": b.description,
            "repro_path": b.repro_path,
            "repro_usage": b.repro_usage,
            "missing_for_full_chain": b.missing_for_full_chain,
            "last_reviewed_at": last_reviewed_at,
            "last_decision": latest_decisions[b.id].decision if b.id in latest_decisions else None,
        }
        for b, last_reviewed_at in rows
    ]


def list_all_bugs_with_review(
    db: Session,
    *,
    project_id: str | None = None,
    scope_id: str | None = None,
    severity: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    latest = (
        select(BugReview.bug_id, func.max(BugReview.created_at).label("last_reviewed_at"))
        .group_by(BugReview.bug_id)
        .subquery()
    )
    q = select(Bug, latest.c.last_reviewed_at).outerjoin(latest, latest.c.bug_id == Bug.id)
    if project_id:
        scope_ids = [s for (s,) in db.execute(
            select(Scope.id).where(Scope.project_id == project_id)
        ).all()]
        q = q.where(Bug.scope_id.in_(scope_ids))
    if scope_id:
        q = q.where(Bug.scope_id == scope_id)
    if severity:
        q = q.where(Bug.severity == severity)
    if search:
        like = f"%{search}%"
        q = q.where(Bug.description.ilike(like))
    rows = db.execute(q).all()
    bug_ids = [b.id for b, _ in rows]
    latest_decisions = _latest_review_per_bug(db, bug_ids)
    scope_meta = {
        s.id: (s.name, s.project_id)
        for s in db.query(Scope).filter(Scope.id.in_({b.scope_id for b, _ in rows})).all()
    }
    return [
        {
            "id": b.id,
            "severity": b.severity,
            "scope_id": b.scope_id,
            "scope_name": scope_meta.get(b.scope_id, (None, None))[0],
            "project_id": scope_meta.get(b.scope_id, (None, None))[1],
            "description": b.description,
            "repro_path": b.repro_path,
            "repro_usage": b.repro_usage,
            "missing_for_full_chain": b.missing_for_full_chain,
            "last_reviewed_at": last_reviewed_at,
            "last_decision": latest_decisions[b.id].decision if b.id in latest_decisions else None,
        }
        for b, last_reviewed_at in rows
    ]


def record_review(
    db: Session,
    *,
    bug_id: str,
    project_id: str,
    run_id: str | None,
    reviewer_role: str,
    decision: str,
    notes: str,
) -> BugReview:
    review = BugReview(
        id=next_id(db, "review"),
        bug_id=bug_id,
        project_id=project_id,
        run_id=run_id,
        reviewer_role=reviewer_role,
        decision=decision,
        notes=notes,
    )
    db.add(review)
    db.flush()
    return review


def list_reviews_for_bug(db: Session, bug_id: str) -> list[BugReview]:
    return list(
        db.execute(
            select(BugReview).where(BugReview.bug_id == bug_id).order_by(desc(BugReview.created_at))
        ).scalars()
    )
