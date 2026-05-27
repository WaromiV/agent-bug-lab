"""
Synchronous dedup agent.

Runs the configured harness inline (not via Arq) to identify duplicate bug
groups in a project, then enforces the deletions server-side after strict
validation. Each delete is paired with a `BugReview` row so the dedup pass
shows up in the per-bug audit trail the same way cleaner-agent removals do.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.paths import write_json
from app.db.models import Bug
from app.services import review_queue, settings_service
from app.services.exporter_service import _bugs_payload
from app.services.harness_runner import get_harness, run_harness
from app.services.prompts import DEDUP_OBJECTIVE

log = get_logger(__name__)


class DedupError(RuntimeError):
    pass


async def run_dedup(db: Session, project) -> dict[str, Any]:
    settings = get_settings()
    cfg = settings_service.get_or_init(db)
    spec = get_harness(cfg.selected_harness)

    bugs = _bugs_payload(db, project.id)
    bug_ids_in_scope = {b["id"] for b in bugs}

    input_payload = {
        "task_id": f"dedup_{project.id}_{int(datetime.now(UTC).timestamp())}",
        "role": "dedup_agent",
        "project": {
            "id": project.id,
            "name": project.name,
            "repo_path": project.repo_path,
        },
        "candidate_count": len(bugs),
        "bugs": bugs,
        "objective": DEDUP_OBJECTIVE,
    }

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    data_dir: Path = settings.data_dir / f"dedup_{project.id}_{ts}"
    data_dir.mkdir(parents=True, exist_ok=True)
    log.info("dedup.start", project_id=project.id, candidates=len(bugs), data_dir=str(data_dir))

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
            "dedup.failed",
            project_id=project.id,
            parse_error=result.parse_error,
            exit_code=result.exit_code,
        )
        raise DedupError(
            result.parse_error or f"dedup agent exited {result.exit_code} with no parseable output"
        )

    groups = result.raw_output.get("duplicate_groups")
    summary = result.raw_output.get("summary") or ""
    if not isinstance(groups, list):
        raise DedupError("dedup agent response missing or non-list `duplicate_groups` field")

    # ── strict validation: every id must belong to this project, no aliasing ──
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            raise DedupError(f"group #{i} is not an object")
        canonical = g.get("canonical_bug_id")
        dups = g.get("duplicate_bug_ids")
        reason = g.get("reason") or "duplicate of canonical"
        if not isinstance(canonical, str) or not isinstance(dups, list):
            raise DedupError(f"group #{i} has wrong types")
        if canonical not in bug_ids_in_scope:
            raise DedupError(f"group #{i}: canonical {canonical!r} not in project")
        if canonical in seen:
            raise DedupError(f"group #{i}: canonical {canonical!r} reused across groups")
        seen.add(canonical)
        bad = [d for d in dups if not isinstance(d, str) or d not in bug_ids_in_scope]
        if bad:
            raise DedupError(f"group #{i}: duplicate ids not in project: {bad}")
        if canonical in dups:
            raise DedupError(f"group #{i}: canonical {canonical!r} listed as its own duplicate")
        for d in dups:
            if d in seen:
                raise DedupError(f"group #{i}: bug {d!r} appears in multiple groups")
            seen.add(d)
        validated.append({"canonical": canonical, "duplicates": list(dups), "reason": reason})

    # ── enforce: delete duplicates, record BugReview rows ──
    deleted_ids: list[str] = []
    kept_ids: list[str] = []
    for g in validated:
        kept_ids.append(g["canonical"])
        for dup_id in g["duplicates"]:
            bug = db.get(Bug, dup_id)
            if bug is None:
                # Race: another caller removed it. Skip silently.
                continue
            review_queue.record_review(
                db,
                bug_id=dup_id,
                project_id=project.id,
                run_id=None,
                reviewer_role="cleaner_agent",
                decision="removed",
                notes=f"dedup: duplicate of {g['canonical']} — {g['reason']}",
            )
            db.delete(bug)
            deleted_ids.append(dup_id)
    db.flush()

    summary_payload = {
        "project_id": project.id,
        "candidates_seen": len(bugs),
        "groups": validated,
        "deleted_bug_ids": deleted_ids,
        "kept_canonical_ids": kept_ids,
        "deleted_count": len(deleted_ids),
        "groups_count": len(validated),
        "model_summary": summary,
        "model": cfg.selected_model,
        "effort": cfg.selected_effort,
        "harness": cfg.selected_harness,
        "data_dir": str(data_dir),
    }
    write_json(data_dir / "dedup_report.json", summary_payload)
    log.info(
        "dedup.done",
        project_id=project.id,
        deleted=len(deleted_ids),
        groups=len(validated),
    )
    return summary_payload
