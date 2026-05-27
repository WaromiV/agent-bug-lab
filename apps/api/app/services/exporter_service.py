"""
Synchronous export agent.

Runs the configured harness inline (not via Arq) so the HTTP request can
return the curated Markdown directly to the browser. Each export is a fresh
read-only pass over every bug already ingested for a project — there is no
DB row for an "exporter run", just a forensic data_dir under data/export_*.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.paths import write_json, write_text
from app.db.models import Project
from app.services import review_queue, settings_service
from app.services.harness_runner import get_harness, run_harness
from app.services.prompts import EXPORTER_OBJECTIVE

log = get_logger(__name__)


class ExportError(RuntimeError):
    """Raised when the export agent fails to produce a usable markdown."""


def _bugs_payload(db: Session, project_id: str) -> list[dict[str, Any]]:
    rows = review_queue.list_all_bugs_with_review(db, project_id=project_id)
    return [
        {
            "id": r["id"],
            "severity": r["severity"],
            "scope_id": r["scope_id"],
            "scope_name": r.get("scope_name"),
            "description": r["description"],
            "repro_path": r["repro_path"],
            "repro_usage": r["repro_usage"],
            "missing_for_full_chain": r["missing_for_full_chain"],
        }
        for r in rows
    ]


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return s or "project"


async def run_export(db: Session, project: Project) -> tuple[str, str]:
    """Run the curation agent and return (markdown, filename).

    The filename is a download-friendly hint; the caller may use it in the
    Content-Disposition header.
    """
    settings = get_settings()
    cfg = settings_service.get_or_init(db)
    spec = get_harness(cfg.selected_harness)

    bugs = _bugs_payload(db, project.id)

    input_payload = {
        "task_id": f"export_{project.id}_{int(datetime.now(UTC).timestamp())}",
        "role": "exporter_agent",
        "project": {
            "id": project.id,
            "name": project.name,
            "repo_path": project.repo_path,
            "bug_bounty_url": project.bug_bounty_url,
        },
        "candidate_count": len(bugs),
        "bugs": bugs,
        "objective": EXPORTER_OBJECTIVE,
    }

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    data_dir: Path = settings.data_dir / f"export_{project.id}_{ts}"
    data_dir.mkdir(parents=True, exist_ok=True)
    log.info("export.start", project_id=project.id, candidates=len(bugs), data_dir=str(data_dir))

    result = await run_harness(
        spec,
        model=cfg.selected_model,
        input_payload=input_payload,
        data_dir=data_dir,
        resume_session=None,
        timeout_seconds=settings.run_timeout_seconds,
        on_line=None,
        effort=cfg.selected_effort,
    )

    if result.parse_error or result.raw_output is None:
        log.error(
            "export.failed",
            project_id=project.id,
            parse_error=result.parse_error,
            exit_code=result.exit_code,
        )
        raise ExportError(
            result.parse_error or f"export agent exited {result.exit_code} with no parseable output"
        )

    markdown = result.raw_output.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        log.error("export.no_markdown_field", project_id=project.id, keys=list(result.raw_output.keys()))
        raise ExportError("export agent response missing or empty `markdown` field")

    write_text(data_dir / "export.md", markdown)
    write_json(
        data_dir / "summary.json",
        {
            "project_id": project.id,
            "candidates_seen": len(bugs),
            "markdown_bytes": len(markdown),
            "model": cfg.selected_model,
            "effort": cfg.selected_effort,
            "harness": cfg.selected_harness,
            "data_dir": str(data_dir),
        },
    )
    log.info("export.done", project_id=project.id, markdown_bytes=len(markdown), data_dir=str(data_dir))

    filename = f"findings_{_slugify(project.name)}_{ts}.md"
    return markdown, filename
