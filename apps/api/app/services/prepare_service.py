"""
Prepare service — orchestrates the two-phase prepare stage:

  1. Static facts (cheap, deterministic; no LLM)        prepare_static.py
  2. Prepare agent (LLM)                                runs via harness_runner

The output of phase 1 is fed as an additional `static_facts` field on the
agent's input JSON. The agent's structured `dossier` output is then saved to
`projects.prepare_dossier` so downstream searcher runs (and the UI) can
consume it.

Validation of the agent output lives here so the rest of the pipeline can
trust `project.prepare_dossier` shape.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.ids import next_id
from app.core.logging import get_logger
from app.core.paths import write_json
from app.db.models import AgentRun, Project
from app.services import run_manager, scope_service
from app.services.prompts import PREPARE_OBJECTIVE

log = get_logger(__name__)


class PrepareOutputError(ValueError):
    """Raised when the prepare agent's output fails the dossier contract."""


def enqueue_prepare(
    db: Session,
    *,
    project: Project,
    harness: str,
    model: str,
    effort: str | None,
) -> AgentRun:
    """Queue a prepare_agent run for `project`. Returns the run row."""
    run_id = next_id(db, "run")
    raw_input = _build_prepare_input(
        task_id=run_id,
        project=project,
        scopes=scope_service.list_for_project(db, project.id),
    )
    return run_manager.create_run(
        db,
        project_id=project.id,
        role="prepare_agent",
        harness=harness,
        model=model,
        effort=effort,
        objective=raw_input["objective"],
        raw_input=raw_input,
        run_id=run_id,
    )


def _build_prepare_input(
    *,
    task_id: str,
    project: Project,
    scopes: list[Any],
) -> dict[str, Any]:
    """Recon agent input.

    The agent reads `project.bug_bounty_url` and does its own research; we
    pass the project block (URL + name + scopes) and nothing else. There is
    no static-facts preflight — the URL may not even point at a repo.
    """
    return {
        "task_id": task_id,
        "role": "prepare_agent",
        "project": {
            "id": project.id,
            "name": project.name,
            "bug_bounty_url": project.bug_bounty_url,
            "repo_path": project.repo_path,
            "scopes": [
                {"id": s.id, "name": s.name, "description": s.description}
                for s in scopes
            ],
        },
        "objective": PREPARE_OBJECTIVE,
        "constraints": {
            "read_only": True,
            "do_not_modify_repo": True,
            "output_format": "json",
            "may_fetch_public_web": True,
        },
    }


def validate_dossier(raw_output: dict[str, Any] | None) -> dict[str, Any]:
    """Strict contract check. Returns the dossier dict on success.

    Mirrors the recon-agent output contract documented in
    `prompts.PREPARE_OBJECTIVE`. Fail loudly on shape drift — a malformed
    dossier silently weakens every downstream searcher prompt.
    """
    if not isinstance(raw_output, dict):
        raise PrepareOutputError("output is not a JSON object")
    status = raw_output.get("status")
    if status != "ok":
        raise PrepareOutputError(f"unexpected status: {status!r}")
    dossier = raw_output.get("dossier")
    if not isinstance(dossier, dict):
        raise PrepareOutputError("`dossier` missing or not an object")

    summary = dossier.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise PrepareOutputError("`dossier.summary` must be a non-empty string")

    target_kind = dossier.get("target_kind")
    if not isinstance(target_kind, str) or not target_kind.strip():
        raise PrepareOutputError("`dossier.target_kind` must be a non-empty string")

    def _list(key: str, *, min_len: int, max_len: int, required: bool = True) -> list[Any]:
        value = dossier.get(key, [] if not required else None)
        if value is None:
            raise PrepareOutputError(f"`dossier.{key}` missing")
        if not isinstance(value, list):
            raise PrepareOutputError(f"`dossier.{key}` must be a list")
        if not (min_len <= len(value) <= max_len):
            raise PrepareOutputError(
                f"`dossier.{key}` length {len(value)} outside [{min_len}, {max_len}]"
            )
        return value

    targets = _list("in_scope_targets", min_len=1, max_len=30)
    target_names: set[str] = set()
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            raise PrepareOutputError(f"in_scope_targets[{i}] not an object")
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PrepareOutputError(f"in_scope_targets[{i}].name must be a non-empty string")
        target_names.add(name)

    _list("attack_surfaces", min_len=1, max_len=12)
    hotspots = _list("candidate_hotspots", min_len=1, max_len=30)
    for i, h in enumerate(hotspots):
        if not isinstance(h, dict):
            raise PrepareOutputError(f"candidate_hotspots[{i}] not an object")
        target_ref = h.get("target")
        if not isinstance(target_ref, str) or not target_ref.strip():
            raise PrepareOutputError(
                f"candidate_hotspots[{i}].target must be a non-empty string"
            )
        score = h.get("score")
        if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
            raise PrepareOutputError(
                f"candidate_hotspots[{i}].score must be a number in [0, 1]"
            )
    # Sort order is a presentation constraint, not a data one. If the
    # agent produced unsorted hotspots, fix in place rather than fail —
    # 10-minute prepare runs are too expensive to discard over this.
    hotspots.sort(key=lambda h: -float(h.get("score", 0.0)))
    dossier["candidate_hotspots"] = hotspots

    # Optional / 0-30 lists. Validate shape if present, length if non-empty.
    _list("prior_audits", min_len=0, max_len=30)
    _list("known_incidents", min_len=0, max_len=30)
    _list("threat_model_notes", min_len=0, max_len=30)
    _list("open_questions", min_len=0, max_len=30)

    # v2 scope-policy fields. Tolerant: missing → empty (older dossiers
    # predate the schema extension). If present, validate shape lightly.
    sev_tiers = dossier.get("severity_tiers")
    if sev_tiers is not None:
        if not isinstance(sev_tiers, list) or len(sev_tiers) > 30:
            raise PrepareOutputError(
                "`dossier.severity_tiers` must be a list of length 0-30"
            )
        for i, t in enumerate(sev_tiers):
            if not isinstance(t, dict):
                raise PrepareOutputError(f"severity_tiers[{i}] not an object")
            name = t.get("name")
            quals = t.get("qualifiers")
            if not isinstance(name, str) or not name.strip():
                raise PrepareOutputError(
                    f"severity_tiers[{i}].name must be a non-empty string"
                )
            if not isinstance(quals, list):
                raise PrepareOutputError(
                    f"severity_tiers[{i}].qualifiers must be a list"
                )

    oos = dossier.get("out_of_scope")
    if oos is not None:
        if not isinstance(oos, list) or len(oos) > 60:
            raise PrepareOutputError(
                "`dossier.out_of_scope` must be a list of length 0-60"
            )
        for i, c in enumerate(oos):
            if not isinstance(c, str):
                raise PrepareOutputError(f"out_of_scope[{i}] must be a string")

    rules = dossier.get("program_rules")
    if rules is not None and not isinstance(rules, dict):
        raise PrepareOutputError("`dossier.program_rules` must be an object")

    return dossier


def save_dossier(
    db: Session,
    *,
    project_id: str,
    run_id: str,
    dossier: dict[str, Any],
    data_dir: Path,
) -> None:
    """Persist dossier on the project row and write the forensic JSON."""
    project = db.get(Project, project_id)
    if project is None:
        raise PrepareOutputError(f"project disappeared while saving dossier: {project_id}")
    project.prepare_dossier = {
        "dossier": dossier,
        "saved_from_run_id": run_id,
    }
    project.prepare_run_id = run_id
    db.flush()
    write_json(data_dir / "dossier.json", dossier)
    log.info(
        "prepare.dossier.saved",
        project_id=project_id,
        run_id=run_id,
        hotspots=len(dossier.get("candidate_hotspots", [])),
        surfaces=len(dossier.get("attack_surfaces", [])),
        targets=len(dossier.get("in_scope_targets", [])),
    )
