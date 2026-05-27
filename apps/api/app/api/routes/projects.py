from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.api.deps import ArqPool, DbSession
from app.core.logging import get_logger
from app.schemas.project import ProjectCreate, ProjectCreateResponse, ProjectRead
from app.services import dedup_service, exporter_service, prepare_service, project_service, settings_service

log = get_logger(__name__)

_IMMUNEFI_RE = re.compile(
    r"https?://(?:www\.)?immunefi\.com/bug-bounty/([a-zA-Z0-9_-]+)"
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DbSession) -> list[ProjectRead]:
    return [ProjectRead.model_validate(p) for p in project_service.list_projects(db)]


@router.post("", response_model=ProjectCreateResponse, status_code=201)
async def create_project(
    payload: ProjectCreate, db: DbSession, pool: ArqPool
) -> ProjectCreateResponse:
    project, run_id = project_service.create_project(db, payload)

    # Auto-scrape Immunefi scope page if the URL matches. Seeds the
    # prepare_dossier with deterministic scope data (severity tiers,
    # out-of-scope, assets) so the LLM prepare agent AND downstream
    # searcher/debate agents have verbatim program rules from the start.
    match = _IMMUNEFI_RE.match(payload.bug_bounty_url)
    if match:
        slug = match.group(1)
        try:
            from app.services.scope_scraper import scrape_scope_full
            scope_data = await scrape_scope_full(slug)
            if scope_data and "error" not in scope_data:
                # Merge into existing dossier or seed a new one
                wrapper = project.prepare_dossier or {}
                dossier = wrapper.get("dossier", {}) if isinstance(wrapper, dict) else {}
                dossier["severity_tiers"] = [
                    {"name": f"{t['category']} {t['severity']}", "qualifiers": t["qualifiers"], "max_payout": "see information page"}
                    for t in scope_data.get("severity_tiers", [])
                ]
                dossier["out_of_scope"] = scope_data.get("out_of_scope_program", []) + scope_data.get("out_of_scope_default", [])
                dossier["program_rules"] = {
                    "poc_required": True,
                    "kyc_required": True,
                    "triaged_by": "Immunefi",
                    "primacy_of_impact": None,
                    "custom_notes": [],
                }
                if scope_data.get("impacts_body"):
                    dossier.setdefault("program_rules", {})["custom_notes"] = [scope_data["impacts_body"]]
                # Preserve any existing dossier fields (summary, hotspots, etc)
                project.prepare_dossier = {**wrapper, "dossier": dossier}
                db.flush()
                log.info(
                    "project.scope_scraped",
                    project_id=project.id,
                    slug=slug,
                    tiers=len(scope_data.get("severity_tiers", [])),
                    oos=len(dossier.get("out_of_scope", [])),
                    assets=len(scope_data.get("assets", [])),
                )
        except Exception as e:  # noqa: BLE001
            # Scraper failure is non-fatal — the LLM prepare agent will
            # still research the URL. Just log and continue.
            log.warning("project.scope_scrape_failed", project_id=project.id, error=str(e)[:200])

    db.commit()
    await pool.enqueue_job("run_prepare", run_id)
    return ProjectCreateResponse(
        project=ProjectRead.model_validate(project),
        prepare_run_id=run_id,
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


@router.post("/{project_id}/start-searcher")
async def start_searcher(
    project_id: str,
    db: DbSession,
    pool: ArqPool,
    count: int = 1,
) -> dict:
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if count < 1 or count > 20:
        raise HTTPException(400, "count must be 1-20")
    cfg = settings_service.get_or_init(db)
    run_ids: list[str] = []
    for _ in range(count):
        run = project_service.enqueue_searcher(
            db,
            project=project,
            harness=cfg.selected_harness,
            model=cfg.selected_model,
            effort=cfg.selected_effort,
        )
        run_ids.append(run.id)
    db.commit()
    for rid in run_ids:
        await pool.enqueue_job("run_searcher", rid)
    return {"run_ids": run_ids, "count": len(run_ids)}


@router.post("/{project_id}/start-prepare", response_model=dict[str, str])
async def start_prepare(project_id: str, db: DbSession, pool: ArqPool) -> dict[str, str]:
    """Queue a fresh prepare/recon run. Used for retries and manual re-runs."""
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    cfg = settings_service.get_or_init(db)
    run = prepare_service.enqueue_prepare(
        db,
        project=project,
        harness=cfg.selected_harness,
        model=cfg.selected_model,
        effort=cfg.selected_effort,
    )
    project.prepare_run_id = run.id
    db.commit()
    await pool.enqueue_job("run_prepare", run.id)
    return {"run_id": run.id}


@router.post("/{project_id}/dedup", response_model=dict)
async def dedup_project(project_id: str, db: DbSession) -> dict:
    """Run the dedup agent synchronously.

    The agent identifies groups of duplicate bugs across all prior runs.
    The server validates every id is in this project and then deletes the
    non-canonical members of each group, recording a `BugReview` audit row
    per deletion. Returns a summary the UI can display.
    """
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    try:
        summary = await dedup_service.run_dedup(db, project)
    except dedup_service.DedupError as e:
        db.rollback()
        raise HTTPException(502, f"dedup agent failed: {e}") from e
    db.commit()
    return summary


@router.post("/{project_id}/export")
async def export_project(project_id: str, db: DbSession) -> Response:
    """Run the curation agent synchronously and return one Markdown file.

    The agent reads every bug ingested for this project and emits a single
    curated `.md` containing only confirmed high-impact findings. The browser
    receives the bytes with a `Content-Disposition: attachment` header so a
    download is triggered immediately on response.
    """
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    try:
        markdown, filename = await exporter_service.run_export(db, project)
    except exporter_service.ExportError as e:
        raise HTTPException(502, f"export agent failed: {e}") from e
    safe = quote(filename)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{safe}',
            "Cache-Control": "no-store",
        },
    )
