from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import next_id
from app.core.logging import get_logger
from app.core.paths import project_dir, write_json, write_text
from app.db.models import Bug, Project, Scope
from app.schemas.project import ProjectCreate
from app.services import prepare_service, run_manager, scope_service, settings_service, static_facts
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
    """Create the project row, its data dir, and queue an initial prepare run.

    Returns (project, prepare_run_id). Caller commits the transaction and
    dispatches the worker job. The prepare run mines static facts about the
    repo and asks the LLM for a threat-model dossier; the searcher is NOT
    auto-chained — the user kicks it off from the project page once they've
    reviewed the dossier.
    """
    settings = get_settings()
    cfg = settings_service.get_or_init(db)
    pid = next_id(db, "project")

    project = Project(
        id=pid,
        name=payload.name,
        bug_bounty_url=payload.bug_bounty_url,
        repo_path=payload.repo_path or str(settings.fixed_repo_root),
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

    run = prepare_service.enqueue_prepare(
        db,
        project=project,
        harness=cfg.selected_harness,
        model=cfg.selected_model,
        effort=cfg.selected_effort,
    )
    project.prepare_run_id = run.id
    db.flush()
    write_text(pdir / "created_prepare_run_id.txt", run.id)
    log.info("prepare.auto_queued", project_id=project.id, run_id=run.id)
    return project, run.id


def enqueue_searcher(
    db: Session,
    *,
    project: Project,
    harness: str,
    model: str,
    effort: str | None,
    resume_from_run_id: str | None = None,
    harness_session_id: str | None = None,
    dossier_override: dict[str, Any] | None = None,
    prior_bugs_override: list[dict[str, Any]] | None = None,
) -> Any:
    """Queue a searcher_agent run.

    By default the input is enriched with the project's own prepare dossier
    (if any) and every prior bug ingested under this project. Callers can
    override either via `dossier_override` / `prior_bugs_override` — e.g. to
    pass a monorepo dossier to a searcher running on a sub-target repo.
    """
    settings = get_settings()
    run_id = next_id(db, "run")

    if dossier_override is not None:
        dossier = dossier_override
    elif project.prepare_dossier is not None:
        # `project.prepare_dossier` is the saved wrapper { dossier, saved_from_run_id, ... };
        # pass the inner `dossier` dict only.
        wrapper = project.prepare_dossier
        dossier = wrapper.get("dossier") if isinstance(wrapper, dict) else None
    else:
        dossier = None

    if prior_bugs_override is not None:
        prior_bugs = prior_bugs_override
    else:
        prior_bugs = _load_prior_bugs(db, project.id)

    raw_input = _build_searcher_input(
        task_id=run_id,
        project=project,
        scopes=scope_service.list_for_project(db, project.id),
        min_findings=settings.searcher_min_findings,
        max_findings=settings.searcher_max_findings,
        prepare_dossier=dossier,
        prior_bugs=prior_bugs,
        static_facts_summary=static_facts.to_agent_summary(project.static_facts),
    )
    return run_manager.create_run(
        db,
        project_id=project.id,
        role="searcher_agent",
        harness=harness,
        model=model,
        effort=effort,
        objective=raw_input["objective"],
        raw_input=raw_input,
        resume_from_run_id=resume_from_run_id,
        harness_session_id=harness_session_id,
        run_id=run_id,
    )


def _load_prior_bugs(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Compact projection of every bug under `project_id`. Joined with scope
    so the searcher sees the scope NAME (not just the project-suffixed id),
    which is what bug patterns cluster around."""
    rows = db.execute(
        select(Bug, Scope.name)
        .join(Scope, Bug.scope_id == Scope.id)
        .where(Scope.project_id == project_id)
        .order_by(Bug.id)
    ).all()
    return [
        {
            "id": b.id,
            "severity": b.severity,
            "scope_name": scope_name,
            "description": b.description,
            "repro_path": b.repro_path,
            "missing_for_full_chain": b.missing_for_full_chain,
        }
        for b, scope_name in rows
    ]


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
    prepare_dossier: dict[str, Any] | None = None,
    prior_bugs: list[dict[str, Any]] | None = None,
    static_facts_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    if prepare_dossier:
        payload["prepare_dossier"] = prepare_dossier
    if prior_bugs:
        # Pass a summary counter instead of the full list. The full list
        # anchors the agent to the severity distribution of existing
        # findings — if 30 prior bugs are all low, the agent calibrates
        # its own findings as low too.
        sev_counts: dict[str, int] = {}
        for b in prior_bugs:
            sev = b.get("severity", "unknown")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        descriptions = [b.get("description", "")[:80] for b in prior_bugs]
        payload["prior_bugs_summary"] = {
            "total": len(prior_bugs),
            "by_severity": sev_counts,
            "note": "These bugs were already found. Do NOT re-report the same mechanisms. But do NOT let their severity distribution influence your own severity assessment — judge each finding independently on its own merits.",
            "descriptions_short": descriptions,
        }
    if static_facts_summary:
        payload["static_facts"] = static_facts_summary
    return payload
