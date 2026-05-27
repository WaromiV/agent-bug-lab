"""
Debate service — orchestrates a multi-turn moderated debate between two
opposing agents about whether a candidate bug is real.

Pipeline (strict; the debate ALWAYS runs to round N):

  for round in 1..N:
      pro_argument = run debater_pro with primary_model
      con_argument = run debater_con with secondary_model
      judge_notes  = run judge_per_round with primary_model
  judge_final = run judge_final with primary_model
      → score (0..10), verdict, winning_side, reasoning

Each sub-call is a real AgentRun row, so existing /runs UI and WS log
streams work without changes. The orchestrator above them lives in this
module.

The `key_unresolved` field on BugDebate is the single piece of evidence a
human reviewer should look at first. The score colors the project-page
chip.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import next_id
from app.core.logging import get_logger
from app.db.models import AgentRun, Bug, BugDebate, BugDebateTurn, Project
from app.db.session import SessionLocal
from app.services import project_service, run_manager, scope_service, static_facts
from app.services.harness_runner import HarnessResult, get_harness, run_harness
from app.services.prompts import (
    DEBATER_CON_OBJECTIVE,
    DEBATER_PRO_OBJECTIVE,
    JUDGE_FINAL_OBJECTIVE,
    JUDGE_PER_ROUND_OBJECTIVE,
)

log = get_logger(__name__)


class DebateError(ValueError):
    pass


# ── public API ──────────────────────────────────────────────────────────────


def start_debate(
    db: Session,
    *,
    bug: Bug,
    project: Project,
    max_rounds: int,
    primary_model: str,
    secondary_model: str,
) -> BugDebate:
    """Create a queued BugDebate row. Caller commits & enqueues run_debate."""
    debate = BugDebate(
        id=next_id(db, "debate"),
        bug_id=bug.id,
        project_id=project.id,
        status="queued",
        max_rounds=max_rounds,
        current_round=0,
        primary_model=primary_model,
        secondary_model=secondary_model,
    )
    db.add(debate)
    db.flush()
    log.info(
        "debate.queued",
        debate_id=debate.id,
        bug_id=bug.id,
        max_rounds=max_rounds,
        primary_model=primary_model,
        secondary_model=secondary_model,
    )
    return debate


def get_debate_with_turns(
    db: Session, debate_id: str
) -> tuple[BugDebate, list[BugDebateTurn]] | None:
    debate = db.get(BugDebate, debate_id)
    if debate is None:
        return None
    turns = list(
        db.execute(
            select(BugDebateTurn)
            .where(BugDebateTurn.debate_id == debate_id)
            .order_by(BugDebateTurn.round.asc(), BugDebateTurn.created_at.asc())
        ).scalars()
    )
    return debate, turns


def latest_debate_for_bug(db: Session, bug_id: str) -> BugDebate | None:
    return db.execute(
        select(BugDebate)
        .where(BugDebate.bug_id == bug_id)
        .order_by(BugDebate.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


# ── orchestrator (called from worker) ───────────────────────────────────────


async def drive_debate(debate_id: str) -> None:
    """Run all N rounds and the final judge. Streams logs through AgentLog
    rows the same way other workers do; the WS log fan-out picks them up.
    """
    with SessionLocal() as s:
        debate = s.get(BugDebate, debate_id)
        if debate is None:
            log.warning("debate.missing", debate_id=debate_id)
            return
        if debate.status not in ("queued", "running"):
            log.info("debate.skip_terminal", debate_id=debate_id, status=debate.status)
            return

        bug = s.get(Bug, debate.bug_id)
        project = s.get(Project, debate.project_id)
        if bug is None or project is None:
            debate.status = "errored"
            debate.error = "bug or project missing"
            debate.finished_at = datetime.now(UTC)
            s.commit()
            return

        from app.services import settings_service

        scopes = scope_service.list_for_project(s, project.id)
        project_block = project_service.project_payload(project, scopes)
        bug_block = _bug_to_block(bug)
        static_facts_summary = static_facts.to_agent_summary(project.static_facts)
        # `project.prepare_dossier` is the wrapper { dossier, saved_from_run_id };
        # pass the inner dossier dict only — agents read its severity_tiers /
        # out_of_scope / program_rules to ground bountiability calls.
        wrapper = project.prepare_dossier
        prepare_dossier = (
            wrapper.get("dossier") if isinstance(wrapper, dict) else None
        )
        max_rounds = debate.max_rounds
        primary_model = debate.primary_model
        secondary_model = debate.secondary_model
        cfg = settings_service.get_or_init(s)
        harness = cfg.selected_harness
        # con runs on `secondary_harness` if set, else falls back to the
        # primary. Enables MDASH-style cross-vendor debate (e.g. claude_code
        # pro/judge vs codex con).
        con_harness = cfg.secondary_harness or harness
        effort = cfg.selected_effort
        project_id_local = project.id

        debate.status = "running"
        s.commit()

    prior_rounds: list[dict[str, Any]] = []

    for round_no in range(1, max_rounds + 1):
        # ── PRO ──
        pro_payload = _build_debater_payload(
            role="debater_pro",
            objective=DEBATER_PRO_OBJECTIVE,
            project_block=project_block,
            bug_block=bug_block,
            static_facts_summary=static_facts_summary,
            prepare_dossier=prepare_dossier,
            round_no=round_no,
            total_rounds=max_rounds,
            prior_rounds=prior_rounds,
        )
        pro_output = await _run_subrun(
            debate_id=debate_id,
            project_id=project_id_local,
            role="debater_pro",
            objective=DEBATER_PRO_OBJECTIVE,
            payload=pro_payload,
            harness=harness,
            model=primary_model,
            effort=effort,
            round_no=round_no,
            side="pro",
        )

        # ── CON ──
        con_payload = _build_debater_payload(
            role="debater_con",
            objective=DEBATER_CON_OBJECTIVE,
            project_block=project_block,
            bug_block=bug_block,
            static_facts_summary=static_facts_summary,
            prepare_dossier=prepare_dossier,
            round_no=round_no,
            total_rounds=max_rounds,
            prior_rounds=prior_rounds + [{"round": round_no, "side": "pro", "payload": pro_output}],
        )
        con_output = await _run_subrun(
            debate_id=debate_id,
            project_id=project_id_local,
            role="debater_con",
            objective=DEBATER_CON_OBJECTIVE,
            payload=con_payload,
            harness=con_harness,
            model=secondary_model,
            effort=effort,
            round_no=round_no,
            side="con",
        )

        # ── JUDGE NOTES (per-round) ──
        notes_payload = {
            "task_id": f"{debate_id}-r{round_no}-notes",
            "role": "judge_per_round",
            "round": round_no,
            "total_rounds": max_rounds,
            "bug": bug_block,
            "pro_argument": pro_output,
            "con_argument": con_output,
            "prior_round_notes": [r.get("notes_md") for r in prior_rounds if r.get("side") == "judge_note"],
            "objective": JUDGE_PER_ROUND_OBJECTIVE,
            "constraints": {"output_format": "json"},
        }
        if static_facts_summary:
            notes_payload["static_facts"] = static_facts_summary
        if prepare_dossier:
            notes_payload["prepare_dossier"] = prepare_dossier
        notes_output = await _run_subrun(
            debate_id=debate_id,
            project_id=project_id_local,
            role="judge_per_round",
            objective=JUDGE_PER_ROUND_OBJECTIVE,
            payload=notes_payload,
            harness=harness,
            model=primary_model,
            effort=effort,
            round_no=round_no,
            side="judge_note",
        )
        notes_md = ""
        if isinstance(notes_output, dict):
            notes_md = str(notes_output.get("notes_md") or "")
        with SessionLocal() as s:
            # Re-record notes_md on the turn we just inserted.
            turn = s.execute(
                select(BugDebateTurn)
                .where(BugDebateTurn.debate_id == debate_id)
                .where(BugDebateTurn.round == round_no)
                .where(BugDebateTurn.side == "judge_note")
                .order_by(BugDebateTurn.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if turn is not None:
                turn.notes_md = notes_md
                s.commit()
            debate = s.get(BugDebate, debate_id)
            if debate is not None:
                debate.current_round = round_no
                s.commit()

        prior_rounds.append({"round": round_no, "side": "pro", "payload": pro_output})
        prior_rounds.append({"round": round_no, "side": "con", "payload": con_output})
        prior_rounds.append({"round": round_no, "side": "judge_note", "notes_md": notes_md})

    # ── FINAL VERDICT ──
    final_payload = {
        "task_id": f"{debate_id}-final",
        "role": "judge_final",
        "total_rounds": max_rounds,
        "bug": bug_block,
        "all_rounds": prior_rounds,
        "objective": JUDGE_FINAL_OBJECTIVE,
        "constraints": {"output_format": "json"},
    }
    if static_facts_summary:
        final_payload["static_facts"] = static_facts_summary
    if prepare_dossier:
        final_payload["prepare_dossier"] = prepare_dossier
    final_output = await _run_subrun(
        debate_id=debate_id,
        project_id=project_id_local,
        role="judge_final",
        objective=JUDGE_FINAL_OBJECTIVE,
        payload=final_payload,
        harness=harness,
        model=primary_model,
        effort=effort,
        round_no=max_rounds,
        side="judge_final",
    )

    with SessionLocal() as s:
        debate = s.get(BugDebate, debate_id)
        if debate is None:
            return
        if not isinstance(final_output, dict):
            debate.status = "errored"
            debate.error = "judge_final produced no output"
            debate.finished_at = datetime.now(UTC)
            s.commit()
            return
        try:
            score = int(final_output.get("score"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            score = None
        verdict = final_output.get("verdict")
        winning_side = final_output.get("winning_side")
        reasoning = final_output.get("reasoning")
        key_unresolved = final_output.get("key_unresolved")
        if not isinstance(score, int) or not (0 <= score <= 10):
            debate.status = "errored"
            debate.error = f"judge_final score invalid: {final_output.get('score')!r}"
        elif verdict not in ("real", "flawed", "rejected"):
            debate.status = "errored"
            debate.error = f"judge_final verdict invalid: {verdict!r}"
        elif winning_side not in ("pro", "con", "tie"):
            debate.status = "errored"
            debate.error = f"judge_final winning_side invalid: {winning_side!r}"
        else:
            debate.status = "finished"
            debate.score = score
            debate.verdict = verdict
            debate.winning_side = winning_side
            debate.reasoning = str(reasoning or "")
            debate.key_unresolved = (
                list(key_unresolved) if isinstance(key_unresolved, list) else None
            )
        debate.finished_at = datetime.now(UTC)
        s.commit()


# ── helpers ─────────────────────────────────────────────────────────────────


def _bug_to_block(bug: Bug) -> dict[str, Any]:
    return {
        "id": bug.id,
        "severity": bug.severity,
        "scope_id": bug.scope_id,
        "description": bug.description,
        "repro_path": bug.repro_path,
        "repro_usage": bug.repro_usage,
        "missing_for_full_chain": bug.missing_for_full_chain,
    }


def _build_debater_payload(
    *,
    role: str,
    objective: str,
    project_block: dict[str, Any],
    bug_block: dict[str, Any],
    static_facts_summary: dict[str, Any] | None,
    prepare_dossier: dict[str, Any] | None,
    round_no: int,
    total_rounds: int,
    prior_rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_id": f"debate-r{round_no}-{role}",
        "role": role,
        "project": project_block,
        "bug": bug_block,
        "round": round_no,
        "total_rounds": total_rounds,
        "prior_rounds": prior_rounds,
        "objective": objective,
        "constraints": {
            "read_only": True,
            "do_not_modify_repo": True,
            "output_format": "json",
        },
    }
    if static_facts_summary:
        payload["static_facts"] = static_facts_summary
    if prepare_dossier:
        payload["prepare_dossier"] = prepare_dossier
    return payload


async def _run_subrun(
    *,
    debate_id: str,
    project_id: str,
    role: str,
    objective: str,
    payload: dict[str, Any],
    harness: str,
    model: str,
    effort: str | None,
    round_no: int,
    side: str,
) -> dict[str, Any] | None:
    """Create+run one harness call as a normal AgentRun, link it to the
    debate via a BugDebateTurn row, return parsed output (or None on
    failure)."""
    # Create the run row & turn.
    with SessionLocal() as s:
        run = run_manager.create_run(
            s,
            project_id=project_id,
            role=role,
            harness=harness,
            model=model,
            effort=effort,
            objective=objective,
            raw_input=payload,
        )
        run_id = run.id
        data_dir = Path(run.data_dir)
        spec_name = run.harness
        turn = BugDebateTurn(
            id=next_id(s, "dturn"),
            debate_id=debate_id,
            round=round_no,
            side=side,
            run_id=run_id,
        )
        s.add(turn)
        run_manager.mark_running(s, run)
        s.commit()

    async def on_line(stream: str, line: str) -> None:
        with SessionLocal() as s2:
            run_manager.append_log(
                s2, run_id, "info", f"harness.{stream}.line", {"line": line}
            )
            s2.commit()

    spec = get_harness(spec_name)
    timeout = get_settings().run_timeout_seconds
    result: HarnessResult = await run_harness(
        spec,
        model=model,
        input_payload=payload,
        data_dir=data_dir,
        resume_session=None,
        timeout_seconds=timeout,
        on_line=on_line,
        effort=effort,
    )

    with SessionLocal() as s:
        run = s.get(AgentRun, run_id)
        if run is None:
            return None
        if result.parse_error or result.raw_output is None:
            run_manager.append_log(
                s,
                run_id,
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
            # Also mark the debate errored so the UI stops spinning.
            debate = s.get(BugDebate, debate_id)
            if debate is not None and debate.status == "running":
                debate.status = "errored"
                debate.error = f"{role} sub-run failed: {result.parse_error}"
                debate.finished_at = datetime.now(UTC)
            s.commit()
            return None

        run_manager.mark_succeeded(s, run, result.raw_output)
        # Persist the parsed payload onto the turn for fast UI rendering.
        turn = s.execute(
            select(BugDebateTurn)
            .where(BugDebateTurn.debate_id == debate_id)
            .where(BugDebateTurn.run_id == run_id)
            .limit(1)
        ).scalar_one_or_none()
        if turn is not None:
            turn.payload = result.raw_output
        s.commit()
        return result.raw_output
