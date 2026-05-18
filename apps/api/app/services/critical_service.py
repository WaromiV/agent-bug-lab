from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.paths import write_json
from app.db.models import AgentRun, Bug, Project
from app.schemas.bug import BugContract
from app.services import project_service, review_queue, run_manager, scope_service
from app.services.prompts import CRITICAL_OBJECTIVE

log = get_logger(__name__)


class CriticalOutputError(ValueError):
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


def build_critical_input(db: Session, *, task_id: str, project: Project, bug: Bug) -> dict[str, Any]:
    scopes = scope_service.list_for_project(db, project.id)
    return {
        "task_id": task_id,
        "role": "critical_thinking_agent",
        "project": project_service.project_payload(project, scopes),
        "bug": _bug_to_contract_dict(bug),
        "objective": CRITICAL_OBJECTIVE,
        "constraints": {
            "read_only": True,
            "output_format": "json",
            "do_not_modify_repo": True,
        },
    }


def queue_critical_run(
    db: Session,
    *,
    project: Project,
    bug: Bug,
    harness: str,
    model: str,
) -> AgentRun:
    from app.core.ids import next_id

    run_id = next_id(db, "run")
    raw_input = build_critical_input(db, task_id=run_id, project=project, bug=bug)
    run = run_manager.create_run(
        db,
        project_id=project.id,
        role="critical_thinking_agent",
        harness=harness,
        model=model,
        objective=raw_input["objective"],
        raw_input=raw_input,
        run_id=run_id,
    )
    write_json(Path(run.data_dir) / "bug_before.json", raw_input["bug"])
    return run


def apply_critical_output(
    db: Session,
    run: AgentRun,
    raw_output: dict[str, Any] | None,
) -> Bug:
    if not isinstance(raw_output, dict):
        raise CriticalOutputError("output is not a JSON object")
    status = raw_output.get("status")
    if status not in ("ok", "failed"):
        raise CriticalOutputError(f"invalid status: {status!r}")
    if status == "failed":
        raise CriticalOutputError(f"harness reported status=failed: {raw_output.get('error') or ''}")

    try:
        scope_service.apply_scope_ops(db, run.project_id, raw_output.get("scope_ops"))
    except scope_service.ScopeOpsError as e:
        raise CriticalOutputError(f"scope_ops failed: {e}") from e

    bug_payload = raw_output.get("bug")
    if not isinstance(bug_payload, dict):
        raise CriticalOutputError("`bug` is not an object")
    try:
        refined = BugContract.model_validate(bug_payload)
    except ValidationError as e:
        raise CriticalOutputError(f"refined bug fails schema: {e}") from e

    original_id = run.raw_input["bug"]["id"]
    original_scope = run.raw_input["bug"]["scope_id"]
    if refined.id != original_id:
        raise CriticalOutputError(f"refined bug id changed: {refined.id} != {original_id}")
    if refined.scope_id != original_scope:
        raise CriticalOutputError(
            f"refined bug scope_id changed: {refined.scope_id} != {original_scope}"
        )

    bug = db.get(Bug, refined.id)
    if bug is None:
        raise CriticalOutputError(f"refined bug {refined.id} no longer exists")

    bug.severity = refined.severity
    bug.description = refined.description
    bug.repro_path = refined.repro_path
    bug.repro_usage = refined.repro_usage
    bug.missing_for_full_chain = refined.missing_for_full_chain
    db.flush()

    notes = str(raw_output.get("review_note") or "refined")
    review_queue.record_review(
        db,
        bug_id=bug.id,
        project_id=run.project_id,
        run_id=run.id,
        reviewer_role="critical_thinking_agent",
        decision="refined",
        notes=notes,
    )

    write_json(Path(run.data_dir) / "bug_after.json", _bug_to_contract_dict(bug))
    log.info("critical.bug.refined", run_id=run.id, bug_id=bug.id)
    return bug
