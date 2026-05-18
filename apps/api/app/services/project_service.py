from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import next_id
from app.core.logging import get_logger
from app.core.paths import project_dir, write_json, write_text
from app.db.models import Project
from app.schemas.project import ProjectCreate
from app.services import run_manager, scope_service, settings_service
from app.services.prompts import SEARCHER_OBJECTIVE

log = get_logger(__name__)


def list_projects(db: Session) -> list[Project]:
    return list(db.execute(select(Project).order_by(Project.created_at.desc())).scalars())


def get(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def delete(db: Session, project: Project) -> None:
    db.delete(project)
    db.flush()


def create_project(db: Session, payload: ProjectCreate) -> tuple[Project, str]:
    """Create the project row, its data dir, and queue an initial searcher run.

    Returns (project, searcher_run_id). Caller is responsible for committing
    the transaction and dispatching the worker job.
    """
    settings = get_settings()
    cfg = settings_service.get_or_init(db)
    pid = next_id(db, "project")

    project = Project(
        id=pid,
        name=payload.name,
        bug_bounty_url=payload.bug_bounty_url,
        repo_path=str(settings.fixed_repo_root),
    )
    db.add(project)
    db.flush()
    log.info("project.created", project_id=project.id, name=project.name)

    pdir = project_dir(project.id)
    write_json(
        pdir / "project.json",
        {
            "id": project.id,
            "name": project.name,
            "bug_bounty_url": project.bug_bounty_url,
            "repo_path": project.repo_path,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        },
    )
    log.info("project.data_dir.created", project_id=project.id, data_dir=str(pdir))

    scope_service.ensure_default(db, project_id=project.id, name=project.name)

    run = enqueue_searcher(db, project=project, harness=cfg.selected_harness, model=cfg.selected_model)
    write_text(pdir / "created_searcher_run_id.txt", run.id)
    log.info("searcher.auto_queued", project_id=project.id, run_id=run.id)
    return project, run.id


def enqueue_searcher(
    db: Session,
    *,
    project: Project,
    harness: str,
    model: str,
    resume_from_run_id: str | None = None,
    harness_session_id: str | None = None,
) -> Any:
    """Queue a searcher_agent run. Used both on project creation and on demand."""
    settings = get_settings()
    # The harness needs the scope vocabulary so it can pick one per finding.
    scope_service.ensure_default(db, project_id=project.id, name=project.name)
    run_id = next_id(db, "run")
    raw_input = _build_searcher_input(
        task_id=run_id,
        project=project,
        scopes=scope_service.list_for_project(db, project.id),
        min_findings=settings.searcher_min_findings,
        max_findings=settings.searcher_max_findings,
    )
    return run_manager.create_run(
        db,
        project_id=project.id,
        role="searcher_agent",
        harness=harness,
        model=model,
        objective=raw_input["objective"],
        raw_input=raw_input,
        resume_from_run_id=resume_from_run_id,
        harness_session_id=harness_session_id,
        run_id=run_id,
    )


def project_payload(project: Project, scopes: list[Any]) -> dict[str, Any]:
    """Common `project` block shared by every agent input. Lives here so all
    three agent contracts stay consistent."""
    return {
        "id": project.id,
        "name": project.name,
        "bug_bounty_url": project.bug_bounty_url,
        "repo_path": project.repo_path,
        "scopes": [
            {"id": s.id, "name": s.name, "description": s.description}
            for s in scopes
        ],
    }


def _build_searcher_input(
    *,
    task_id: str,
    project: Project,
    scopes: list[Any],
    min_findings: int,
    max_findings: int,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "role": "searcher_agent",
        "project": project_payload(project, scopes),
        "objective": SEARCHER_OBJECTIVE,
        "constraints": {
            "read_only": True,
            "min_findings": min_findings,
            "max_findings": max_findings,
            "output_format": "json",
            "do_not_modify_repo": True,
        },
        "required_bug_fields": [
            "id",
            "severity",
            "scope_id",
            "description",
            "repro_path",
            "repro_usage",
            "missing_for_full_chain",
        ],
    }
