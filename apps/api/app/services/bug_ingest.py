from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.ids import next_id
from app.core.logging import get_logger
from app.core.paths import write_json
from app.db.models import AgentRun, Bug
from app.schemas.bug import BugContract
from app.services import scope_service

log = get_logger(__name__)


class SearcherOutputError(ValueError):
    pass


def validate_and_ingest(
    db: Session,
    run: AgentRun,
    raw_output: dict[str, Any] | None,
    *,
    min_findings: int,
    max_findings: int,
) -> list[Bug]:
    """
    Validate a searcher output payload and insert every bug it produced.

    Raises SearcherOutputError on contract failures.
    """
    if not isinstance(raw_output, dict):
        raise SearcherOutputError("output is not a JSON object")
    status = raw_output.get("status")
    if status not in ("ok", "failed"):
        raise SearcherOutputError(f"invalid status: {status!r}")
    if status == "failed":
        raise SearcherOutputError(f"harness reported status=failed: {raw_output.get('error') or ''}")

    bugs_payload = raw_output.get("bugs")
    if not isinstance(bugs_payload, list):
        raise SearcherOutputError("`bugs` is not a list")
    if not (min_findings <= len(bugs_payload) <= max_findings):
        raise SearcherOutputError(
            f"bugs length {len(bugs_payload)} outside [{min_findings}, {max_findings}]"
        )

    # Process scope_ops first: agents may have created or renamed scopes in
    # this run. Bugs may legitimately reference the newly-created scope ids.
    try:
        id_map = scope_service.apply_scope_ops(db, run.project_id, raw_output.get("scope_ops"))
    except scope_service.ScopeOpsError as e:
        raise SearcherOutputError(f"scope_ops failed: {e}") from e

    allowed_scopes = {s.id for s in scope_service.list_for_project(db, run.project_id)}
    if not allowed_scopes:
        raise SearcherOutputError(
            f"project {run.project_id!r} has no scopes defined; cannot ingest"
        )

    validated: list[BugContract] = []
    for i, item in enumerate(bugs_payload):
        if not isinstance(item, dict):
            raise SearcherOutputError(f"bugs[{i}] is not an object")
        try:
            parsed = BugContract.model_validate(item)
        except ValidationError as e:
            raise SearcherOutputError(f"bugs[{i}] fails schema: {e}") from e
        try:
            resolved = scope_service.resolve_scope_id(
                db, run.project_id, parsed.scope_id, id_map
            )
        except scope_service.ScopeOpsError as e:
            raise SearcherOutputError(
                f"bugs[{i}].scope_id={parsed.scope_id!r}: {e}"
            ) from e
        if resolved not in allowed_scopes:
            raise SearcherOutputError(
                f"bugs[{i}].scope_id={parsed.scope_id!r} resolved to {resolved!r} which "
                f"is not one of the project's scopes ({sorted(allowed_scopes)})"
            )
        # Carry the resolved id back through the contract object.
        parsed = parsed.model_copy(update={"scope_id": resolved})
        validated.append(parsed)

    inserted: list[Bug] = []
    for parsed in validated:
        new_id = next_id(db, "bug")
        bug = Bug(
            id=new_id,
            severity=parsed.severity,
            scope_id=parsed.scope_id,
            description=parsed.description,
            repro_path=parsed.repro_path,
            repro_usage=parsed.repro_usage,
            missing_for_full_chain=parsed.missing_for_full_chain,
            owner_run_id=run.id,
        )
        db.add(bug)
        inserted.append(bug)
    db.flush()

    log.info(
        "bugs.ingested",
        run_id=run.id,
        project_id=run.project_id,
        count=len(inserted),
        bug_ids=[b.id for b in inserted],
    )

    from pathlib import Path

    write_json(
        Path(run.data_dir) / "validated_bugs.json",
        [
            {
                "id": b.id,
                "severity": b.severity,
                "scope_id": b.scope_id,
                "description": b.description,
                "repro_path": b.repro_path,
                "repro_usage": b.repro_usage,
                "missing_for_full_chain": b.missing_for_full_chain,
            }
            for b in inserted
        ],
    )
    return inserted
