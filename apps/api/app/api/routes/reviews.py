from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import ArqPool, DbSession
from app.db.models import Bug, Project, Scope
from app.schemas.bug import BugListItem
from app.schemas.review import CleanRequest, CriticalRequest
from app.schemas.run import RunRead
from app.services import cleaner_service, critical_service, review_queue, settings_service

router = APIRouter(prefix="/review-queue", tags=["reviews"])


@router.get("", response_model=list[BugListItem])
def get_queue(db: DbSession, project_id: str | None = None) -> list[BugListItem]:
    return [
        BugListItem.model_validate(r)
        for r in review_queue.list_review_queue(db, project_id=project_id)
    ]


def _project_for_bugs(db, bug_ids: list[str]) -> tuple[Project, list[Bug]]:
    bugs = list(db.query(Bug).filter(Bug.id.in_(bug_ids)).all())
    if len(bugs) != len(bug_ids):
        raise HTTPException(404, "one or more bug ids not found")
    scope_ids = {b.scope_id for b in bugs}
    project_ids = {
        s.project_id
        for s in db.query(Scope).filter(Scope.id.in_(scope_ids)).all()
    }
    if len(project_ids) != 1:
        raise HTTPException(400, "selected bugs span multiple projects; select one project at a time")
    project = db.get(Project, project_ids.pop())
    if project is None:
        raise HTTPException(404, "project not found")
    return project, bugs


@router.post("/clean", response_model=RunRead, status_code=201)
async def clean(payload: CleanRequest, db: DbSession, pool: ArqPool) -> RunRead:
    project, bugs = _project_for_bugs(db, payload.bug_ids)
    cfg = settings_service.get_or_init(db)
    run = cleaner_service.queue_cleaner_run(
        db,
        project=project,
        bugs=bugs,
        harness=cfg.selected_harness,
        model=cfg.selected_model,
    )
    db.commit()
    await pool.enqueue_job("run_cleaner", run.id)
    return RunRead.model_validate(run)


@router.post("/critical", response_model=RunRead, status_code=201)
async def critical(payload: CriticalRequest, db: DbSession, pool: ArqPool) -> RunRead:
    project, bugs = _project_for_bugs(db, [payload.bug_id])
    cfg = settings_service.get_or_init(db)
    run = critical_service.queue_critical_run(
        db,
        project=project,
        bug=bugs[0],
        harness=cfg.selected_harness,
        model=cfg.selected_model,
    )
    db.commit()
    await pool.enqueue_job("run_critical", run.id)
    return RunRead.model_validate(run)
