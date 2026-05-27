"""
Prepare worker — drives a `prepare_agent` run.

The agent is a RECON agent. Its only input is the user-provided
`bug_bounty_url` (which can be an Immunefi page, an audit firm summary, a
GitHub org link, a blog post — anything the user shoves in). The agent goes
out and identifies in-scope repos / contracts / services, pulls history and
lore for each (prior audits, known incidents, scope language), and emits a
structured dossier.

Phase 0.5: static-facts pass. If `project.repo_path` points to a Solidity
target, we run slither + forge inspect synchronously BEFORE the LLM call
and persist the result onto `projects.static_facts`. The agent's input
JSON also gets a compact summary so it can cross-reference the dossier
against deterministic ground truth (callgraph, external surface,
delegatecall sinks, storage layout, modifier coverage). Best-effort:
failures log and the agent runs without facts.

Lifecycle (queued → running → succeeded|failed) is owned here directly
because the apply_output step also writes the dossier onto the Project row,
which `drive_run`'s generic callback signature doesn't quite fit.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AgentRun, Project
from app.db.session import SessionLocal
from app.services import prepare_service, run_manager, static_facts
from app.services.harness_runner import HarnessResult, get_harness, run_harness

log = get_logger(__name__)


async def _emit_log(run_id: str, level: str, message: str, payload: dict[str, Any] | None = None) -> None:
    """Append a log row that the WS pump will push to subscribers."""
    with SessionLocal() as s:
        run_manager.append_log(s, run_id, level, message, payload)
        s.commit()


async def run_prepare(ctx: dict[str, Any], run_id: str) -> None:  # noqa: ARG001
    # ── phase 0: load + mark running ──
    with SessionLocal() as s:
        run = s.get(AgentRun, run_id)
        if run is None:
            log.warning("worker.run_missing", run_id=run_id)
            return
        if run.status not in ("queued", "running"):
            log.info("worker.skip_terminal_run", run_id=run_id, status=run.status)
            return
        run_manager.mark_running(s, run)
        spec_name = run.harness
        model = run.model
        effort = run.effort
        raw_input = dict(run.raw_input)
        data_dir = Path(run.data_dir)
        project_id = run.project_id
        bounty_url = raw_input.get("project", {}).get("bug_bounty_url", "")
        run_manager.append_log(
            s,
            run.id,
            "info",
            "prepare.run.started",
            {"data_dir": str(data_dir), "bug_bounty_url": bounty_url},
        )
        repo_path = run.raw_input.get("project", {}).get("repo_path", "")
        s.commit()

    # ── phase 0.5: static facts (Solidity targets only) ──
    static_facts_summary: dict[str, Any] | None = None
    if repo_path:
        await _emit_log(
            run_id,
            "info",
            "prepare.phase.static_facts.start",
            {"repo_path": repo_path},
        )
        try:
            # collect() is blocking (rsync + forge build + slither); run
            # in a worker thread so the arq event loop stays responsive.
            facts = await asyncio.to_thread(
                static_facts.collect, project_id, Path(repo_path)
            )
            static_facts_summary = static_facts.to_agent_summary(facts)
            with SessionLocal() as s:
                project = s.get(Project, project_id)
                if project is not None:
                    project.static_facts = facts
                    project.static_facts_generated_at = datetime.now(timezone.utc)
                    s.commit()
            await _emit_log(
                run_id,
                "info",
                "prepare.phase.static_facts.done",
                {"stats": facts.get("stats", {}), "errors": len(facts.get("errors", []))},
            )
        except Exception as e:  # noqa: BLE001
            # Don't fail the prepare run — the LLM can still produce a
            # dossier without static facts. Just log + continue.
            await _emit_log(
                run_id,
                "warning",
                "prepare.phase.static_facts.failed",
                {"error": str(e)[:400]},
            )

    # Inject static_facts summary into agent input so the LLM sees it.
    if static_facts_summary is not None:
        raw_input["static_facts"] = static_facts_summary

    # ── phase 1: LLM recon agent ──
    await _emit_log(
        run_id,
        "info",
        "prepare.phase.recon.start",
        {"harness": spec_name, "model": model, "bug_bounty_url": bounty_url},
    )

    async def on_line(stream: str, line: str) -> None:
        await _emit_log(run_id, "info", f"harness.{stream}.line", {"line": line})

    spec = get_harness(spec_name)
    timeout = get_settings().run_timeout_seconds
    result: HarnessResult = await run_harness(
        spec,
        model=model,
        input_payload=raw_input,
        data_dir=data_dir,
        resume_session=None,
        timeout_seconds=timeout,
        on_line=on_line,
        effort=effort,
    )
    await _emit_log(
        run_id,
        "info",
        "prepare.phase.recon.done",
        {"exit_code": result.exit_code, "parse_error": result.parse_error},
    )

    # ── phase 2: validate + save dossier ──
    with SessionLocal() as s:
        run = s.get(AgentRun, run_id)
        if run is None:
            log.warning("worker.run_disappeared", run_id=run_id)
            return

        if result.parse_error or result.raw_output is None:
            run_manager.append_log(
                s,
                run.id,
                "error",
                "harness.output.invalid",
                {"parse_error": result.parse_error, "exit_code": result.exit_code},
            )
            run_manager.mark_failed(
                s,
                run,
                error=result.parse_error or f"harness exited with code {result.exit_code}",
                raw_output=None,
            )
            s.commit()
            return

        try:
            dossier = prepare_service.validate_dossier(result.raw_output)
            prepare_service.save_dossier(
                s,
                project_id=project_id,
                run_id=run.id,
                dossier=dossier,
                data_dir=data_dir,
            )
        except prepare_service.PrepareOutputError as e:
            run_manager.append_log(
                s, run.id, "error", "prepare.dossier.invalid", {"error": str(e)}
            )
            run_manager.mark_failed(s, run, error=str(e), raw_output=result.raw_output)
            s.commit()
            return

        run_manager.append_log(s, run.id, "info", "prepare.dossier.saved", None)
        run_manager.mark_succeeded(s, run, result.raw_output)
        s.commit()
