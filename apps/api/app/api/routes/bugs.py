from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.core.ids import next_id
from app.db.models import Bug, Scope
from app.schemas.bug import BugCreate, BugListItem, BugPatch, BugRead
from app.services import exporter, review_queue

router = APIRouter(prefix="/bugs", tags=["bugs"])


@router.get("", response_model=list[BugListItem])
def list_bugs(
    db: DbSession,
    project_id: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> list[BugListItem]:
    rows = review_queue.list_all_bugs_with_review(
        db, project_id=project_id, scope_id=scope_id, severity=severity, search=search
    )
    return [BugListItem.model_validate(r) for r in rows]


@router.post("", response_model=BugRead, status_code=201)
def create_bug(payload: BugCreate, db: DbSession) -> BugRead:
    bid = next_id(db, "bug")
    bug = Bug(
        id=bid,
        severity=payload.severity,
        scope_id=payload.scope_id,
        description=payload.description,
        repro_path=payload.repro_path,
        repro_usage=payload.repro_usage,
        missing_for_full_chain=payload.missing_for_full_chain,
    )
    db.add(bug)
    db.flush()
    return BugRead.model_validate(_dict(bug, db))


@router.get("/{bug_id}", response_model=BugRead)
def get_bug(bug_id: str, db: DbSession) -> BugRead:
    bug = db.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(404, "bug not found")
    return BugRead.model_validate(_dict(bug, db))


@router.patch("/{bug_id}", response_model=BugRead)
def patch_bug(bug_id: str, payload: BugPatch, db: DbSession) -> BugRead:
    bug = db.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(404, "bug not found")
    updates = payload.model_dump(exclude_none=True)
    if "scope_id" in updates:
        target = db.get(Scope, updates["scope_id"])
        current = db.get(Scope, bug.scope_id)
        if target is None:
            raise HTTPException(404, "target scope not found")
        if current is not None and target.project_id != current.project_id:
            raise HTTPException(400, "cannot move bug to a scope in a different project")
    for k, v in updates.items():
        setattr(bug, k, v)
    db.flush()
    return BugRead.model_validate(_dict(bug, db))


@router.delete("/{bug_id}", status_code=204)
def delete_bug(bug_id: str, db: DbSession) -> None:
    bug = db.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(404, "bug not found")
    review_queue.record_review(
        db,
        bug_id=bug.id,
        project_id=bug.scope_id,
        run_id=None,
        reviewer_role="human",
        decision="removed",
        notes="manually deleted via API",
    )
    db.delete(bug)
    db.flush()


@router.post("/export")
def export_bugs_endpoint(
    db: DbSession,
    project_id: str | None = Query(default=None),
) -> list[dict]:
    return exporter.export_bugs(db, project_id=project_id)


def _dict(b: Bug, db=None) -> dict:
    base = {
        "id": b.id,
        "severity": b.severity,
        "scope_id": b.scope_id,
        "description": b.description,
        "repro_path": b.repro_path,
        "repro_usage": b.repro_usage,
        "missing_for_full_chain": b.missing_for_full_chain,
        "scope_name": None,
        "project_id": None,
    }
    if db is not None:
        scope = db.get(Scope, b.scope_id)
        if scope is not None:
            base["scope_name"] = scope.name
            base["project_id"] = scope.project_id
    return base
