"""
Debate endpoints — start a debate on a bug, fetch the transcript.

A debate is composed of N rounds of (debater_pro, debater_con, judge_per_round)
followed by one judge_final. The orchestration runs as an arq job; each
sub-step is a normal AgentRun whose logs stream over the existing /api/runs
WebSocket. The transcript here is the union of the debate row + ordered
turns + parsed payloads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ArqPool, DbSession
from app.db.models import Bug, Project
from app.services import debate_service, settings_service

router = APIRouter(prefix="/bugs", tags=["debates"])


class DebateStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_rounds: int | None = Field(default=None, ge=1, le=20)


class DebateTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    round: int
    side: str
    run_id: str | None
    payload: dict[str, Any] | None
    notes_md: str | None
    created_at: datetime


class DebateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bug_id: str
    project_id: str
    status: str
    max_rounds: int
    current_round: int
    primary_model: str
    secondary_model: str
    score: int | None
    verdict: str | None
    winning_side: str | None
    reasoning: str | None
    key_unresolved: list[str] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class DebateTranscript(BaseModel):
    debate: DebateRead
    turns: list[DebateTurnRead]


@router.post("/{bug_id}/debate", response_model=DebateRead, status_code=201)
async def start_debate(
    bug_id: str,
    payload: DebateStartRequest,
    db: DbSession,
    pool: ArqPool,
) -> DebateRead:
    bug = db.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(404, "bug not found")
    scope = bug.scope_id
    from app.db.models import Scope

    scope_row = db.get(Scope, scope)
    if scope_row is None:
        raise HTTPException(404, "bug's scope is missing")
    project = db.get(Project, scope_row.project_id)
    if project is None:
        raise HTTPException(404, "project not found for bug")

    cfg = settings_service.get_or_init(db)
    primary = cfg.selected_model
    secondary = cfg.secondary_model or cfg.selected_model
    rounds = payload.max_rounds if payload.max_rounds is not None else cfg.debate_max_rounds

    debate = debate_service.start_debate(
        db,
        bug=bug,
        project=project,
        max_rounds=rounds,
        primary_model=primary,
        secondary_model=secondary,
    )
    db.commit()

    await pool.enqueue_job("run_debate", debate.id)
    return DebateRead.model_validate(debate)


@router.get("/{bug_id}/debate", response_model=DebateTranscript | None)
def get_latest_debate(bug_id: str, db: DbSession) -> DebateTranscript | None:
    if db.get(Bug, bug_id) is None:
        raise HTTPException(404, "bug not found")
    debate = debate_service.latest_debate_for_bug(db, bug_id)
    if debate is None:
        return None
    result = debate_service.get_debate_with_turns(db, debate.id)
    if result is None:
        return None
    debate_row, turns = result
    return DebateTranscript(
        debate=DebateRead.model_validate(debate_row),
        turns=[DebateTurnRead.model_validate(t) for t in turns],
    )
