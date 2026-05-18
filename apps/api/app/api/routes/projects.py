from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import ArqPool, DbSession
from app.schemas.project import ProjectCreate, ProjectCreateResponse, ProjectRead
from app.services import project_service, settings_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DbSession) -> list[ProjectRead]:
    return [ProjectRead.model_validate(p) for p in project_service.list_projects(db)]


@router.post("", response_model=ProjectCreateResponse, status_code=201)
async def create_project(
    payload: ProjectCreate, db: DbSession, pool: ArqPool
) -> ProjectCreateResponse:
    project, run_id = project_service.create_project(db, payload)
    db.commit()
    await pool.enqueue_job("run_searcher", run_id)
    return ProjectCreateResponse(
        project=ProjectRead.model_validate(project),
        searcher_run_id=run_id,
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: DbSession) -> ProjectRead:
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: DbSession) -> None:
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    project_service.delete(db, project)


@router.post("/{project_id}/start-searcher", response_model=dict[str, str])
async def start_searcher(project_id: str, db: DbSession, pool: ArqPool) -> dict[str, str]:
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    cfg = settings_service.get_or_init(db)
    run = project_service.enqueue_searcher(
        db, project=project, harness=cfg.selected_harness, model=cfg.selected_model
    )
    db.commit()
    await pool.enqueue_job("run_searcher", run.id)
    return {"run_id": run.id}
