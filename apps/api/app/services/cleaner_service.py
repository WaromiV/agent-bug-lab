from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.ids import next_id
from app.core.logging import get_logger
from app.core.paths import write_json
from app.db.models import AgentRun, Bug, Project
from app.services import project_service, review_queue, run_manager, scope_service
from app.services.prompts import CLEANER_OBJECTIVE

log = get_logger(__name__)


class CleanerOutputError(ValueError):
    pass


def _bug_to_contract_dict(b: Bug) -> dict[str, Any]:
    return {
        "id": b.id,
        "severity": b.severity,
        "scope_id": b.scope_id,
        "description": b.description,
        "repro_path": b.repro_path,
        "repro_usage": b.repro_usage,
        "missing_for_full_chain": b.missing_for_full_chain,
    }


def build_cleaner_input(
    db: Session,
    *,
    task_id: str,
    project: Project,
    bugs: list[Bug],
) -> dict[str, Any]:
    scopes = scope_service.list_for_project(db, project.id)
    return {
        "task_id": task_id,
        "role": "cleaner_agent",
        "project": project_service.project_payload(project, scopes),
        "selected_bugs": [_bug_to_contract_dict(b) for b in bugs],
        "objective": CLEANER_OBJECTIVE,
        "constraints": {
            "read_only": True,
            "output_format": "json",
            "do_not_modify_repo": True,
        },
    }


def queue_cleaner_run(
    db: Session,
    *,
    project: Project,
    bugs: list[Bug],
    harness: str,
    model: str,
    effort: str | None,
) -> AgentRun:
    """Create a cleaner_agent run and snapshot the selected bugs."""
    if not bugs:
        raise ValueError("cleaner run requires at least one selected bug")
    review_id = next_id(db, "review")
    raw_input = build_cleaner_input(db, task_id=review_id, project=project, bugs=bugs)
    run = run_manager.create_run(
        db,
        project_id=project.id,
        role="cleaner_agent",
        harness=harness,
        model=model,
        effort=effort,
        objective=raw_input["objective"],
        raw_input=raw_input,
    )
    write_json(
        Path(run.data_dir) / "selected_bugs_before.json",
        raw_input["selected_bugs"],
    )
    return run


def _apply_agent_bug_scope_changes(
    db: Session,
    run: AgentRun,
    raw_output: dict[str, Any],
    id_map: dict[str, str],
) -> int:
    """Honor `bug_scope_changes`, but only for bugs whose owner_run_id matches
    this run. Other ids are logged and ignored. Returns the count applied."""
    changes = raw_output.get("bug_scope_changes") or []
    if not isinstance(changes, list):
        raise CleanerOutputError("bug_scope_changes must be an array")
    applied = 0
    for entry in changes:
        if not isinstance(entry, dict):
            raise CleanerOutputError("bug_scope_changes[*] must be objects")
        bug_id = entry.get("bug_id")
        new_scope_id = entry.get("scope_id")
        if not bug_id or not new_scope_id:
            raise CleanerOutputError("bug_scope_changes[*] needs bug_id and scope_id")
        bug = db.get(Bug, bug_id)
        if bug is None:
            log.warning("cleaner.bug_scope_change.bug_missing", bug_id=bug_id)
            continue
        if bug.owner_run_id != run.id:
            log.warning(
                "cleaner.bug_scope_change.rejected_not_owner",
                run_id=run.id,
                bug_id=bug_id,
                owner=bug.owner_run_id,
            )
            continue
        resolved = scope_service.resolve_scope_id(db, run.project_id, new_scope_id, id_map)
        bug.scope_id = resolved
        applied += 1
    if applied:
        db.flush()
    return applied


def apply_cleaner_output(
    db: Session,
    run: AgentRun,
    raw_output: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Validate cleaner output, delete bugs in remove_bug_ids, write reviews for
    every decision, and persist artifact files. Returns a small summary dict.
    """
    if not isinstance(raw_output, dict):
        raise CleanerOutputError("output is not a JSON object")
    status = raw_output.get("status")
    if status not in ("ok", "failed"):
        raise CleanerOutputError(f"invalid status: {status!r}")
    if status == "failed":
        raise CleanerOutputError(f"harness reported status=failed: {raw_output.get('error') or ''}")

    try:
        id_map = scope_service.apply_scope_ops(db, run.project_id, raw_output.get("scope_ops"))
    except scope_service.ScopeOpsError as e:
        raise CleanerOutputError(f"scope_ops failed: {e}") from e
    retags = _apply_agent_bug_scope_changes(db, run, raw_output, id_map)

    selected_ids: set[str] = {b["id"] for b in run.raw_input.get("selected_bugs", [])}
    remove_ids = raw_output.get("remove_bug_ids") or []
    keep_ids = raw_output.get("keep_bug_ids") or []
    decisions = raw_output.get("decisions") or []
    if not isinstance(remove_ids, list) or not isinstance(keep_ids, list):
        raise CleanerOutputError("remove_bug_ids / keep_bug_ids must be arrays")
    if not isinstance(decisions, list):
        raise CleanerOutputError("decisions must be an array")

    rid_set = set(remove_ids)
    kid_set = set(keep_ids)
    unknown = (rid_set | kid_set) - selected_ids
    if unknown:
        raise CleanerOutputError(f"unknown bug ids in output: {sorted(unknown)}")

    decisions_by_bug: dict[str, dict[str, Any]] = {}
    for d in decisions:
        if not isinstance(d, dict):
            raise CleanerOutputError("decision entry is not an object")
        bug_id = d.get("bug_id")
        decision = d.get("decision")
        reason = d.get("reason")
        if not bug_id or not decision or not reason:
            raise CleanerOutputError(f"decision entry missing fields: {d}")
        decisions_by_bug[bug_id] = d

    for bid in rid_set:
        if decisions_by_bug.get(bid, {}).get("reason") in (None, ""):
            raise CleanerOutputError(f"removed bug {bid} has no decision reason")

    removed_snapshots: list[dict[str, Any]] = []
    kept_snapshots: list[dict[str, Any]] = []

    for bug in list(db.query(Bug).filter(Bug.id.in_(selected_ids))):
        snap = _bug_to_contract_dict(bug)
        d = decisions_by_bug.get(bug.id, {"decision": "kept", "reason": "no decision; default keep"})
        notes = d.get("reason", "")
        if bug.id in rid_set:
            review_queue.record_review(
                db,
                bug_id=bug.id,
                project_id=run.project_id,
                run_id=run.id,
                reviewer_role="cleaner_agent",
                decision="removed",
                notes=notes,
            )
            db.delete(bug)
            removed_snapshots.append(snap)
            log.info("cleaner.bug.removed", run_id=run.id, bug_id=bug.id, reason=notes)
        else:
            review_queue.record_review(
                db,
                bug_id=bug.id,
                project_id=run.project_id,
                run_id=run.id,
                reviewer_role="cleaner_agent",
                decision="kept",
                notes=notes,
            )
            kept_snapshots.append(snap)
    db.flush()

    data_dir = Path(run.data_dir)
    write_json(data_dir / "removed_bugs.json", removed_snapshots)
    write_json(data_dir / "kept_bugs.json", kept_snapshots)
    write_json(data_dir / "review_notes.json", list(decisions_by_bug.values()))

    log.info(
        "cleaner.bugs.removed",
        run_id=run.id,
        project_id=run.project_id,
        removed=len(removed_snapshots),
        kept=len(kept_snapshots),
        retagged=retags,
    )
    return {"removed": len(removed_snapshots), "kept": len(kept_snapshots), "retagged": retags}
