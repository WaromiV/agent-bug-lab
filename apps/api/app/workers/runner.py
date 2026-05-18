"""
Shared worker plumbing.

`drive_run` is the single function every worker uses. It loads the run, marks
it running, invokes the harness, persists logs as they stream in, and hands
the parsed output to a per-role apply() callback. Lifecycle (queued → running
→ succeeded|failed) lives here exactly once.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AgentRun
from app.db.session import SessionLocal
from app.services import run_manager
from app.services.harness_runner import HarnessResult, get_harness, run_harness

log = get_logger(__name__)

ApplyOutput = Callable[[Session, AgentRun, dict[str, Any]], None]
"""apply(session, run, raw_output) — role-specific validation/persistence."""


async def drive_run(run_id: str, apply_output: ApplyOutput) -> None:
    """Drive a queued run to terminal state.

    Each phase opens its own session so partial work survives if a later phase
    fails. The DB is the source of truth; data_dir is a forensic trail.
    """
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
        raw_input = dict(run.raw_input)
        data_dir = Path(run.data_dir)
        resume_session = run.harness_session_id if run.resume_from_run_id else None
        run_manager.append_log(s, run.id, "info", "harness.input.created", {"data_dir": str(data_dir)})
        s.commit()

    spec = get_harness(spec_name)
    timeout = get_settings().run_timeout_seconds

    async def on_line(stream: str, line: str) -> None:
        with SessionLocal() as ls:
            run_manager.append_log(
                ls,
                run_id,
                "info",
                f"harness.{stream}.line",
                {"line": line},
            )
            ls.commit()

    log.info("harness.process.spawned", run_id=run_id, harness=spec.name)
    result: HarnessResult = await run_harness(
        spec,
        model=model,
        input_payload=raw_input,
        data_dir=data_dir,
        resume_session=resume_session,
        timeout_seconds=timeout,
        on_line=on_line,
    )
    log.info(
        "harness.output.received",
        run_id=run_id,
        exit_code=result.exit_code,
        parse_error=result.parse_error,
    )

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
            apply_output(s, run, result.raw_output)
        except Exception as e:  # noqa: BLE001
            run_manager.append_log(
                s, run.id, "error", "apply_output.failed", {"error": str(e)}
            )
            run_manager.mark_failed(s, run, error=str(e), raw_output=result.raw_output)
            s.commit()
            return

        run_manager.append_log(s, run.id, "info", "harness.output.validated", None)
        run_manager.mark_succeeded(s, run, result.raw_output)
        s.commit()
