from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    bug_bounty_url: Mapped[str] = mapped_column(Text, nullable=False)
    repo_path: Mapped[str] = mapped_column(Text, nullable=False)
    prepare_dossier: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prepare_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    static_facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    static_facts_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Scope(Base):
    """A scope item under a project — e.g. `Firefox Desktop`, `*.mozilla.org`.

    A bug is filed against exactly one scope. Scopes are owned by a project
    so different audit targets can carry distinct scope vocabularies.
    """
    __tablename__ = "scopes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Bug(Base):
    """The 7-field bug contract plus owner_run_id (the run that created it).
    `owner_run_id` is nullable to allow manual/legacy bugs; agents may only
    retag bugs whose owner_run_id equals their current run id.
    """
    __tablename__ = "bugs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, ForeignKey("scopes.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    repro_path: Mapped[str] = mapped_column(Text, nullable=False)
    repro_usage: Mapped[str] = mapped_column(Text, nullable=False)
    missing_for_full_chain: Mapped[str] = mapped_column(Text, nullable=False)
    owner_run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("agent_runs.id"), nullable=True
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    harness: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    effort: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    resume_from_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    harness_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_dir: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(Text, ForeignKey("agent_runs.id"), nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BugReview(Base):
    """bug_id has NO FK — cleaner-agent may delete bugs; reviews must survive."""
    __tablename__ = "bug_reviews"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    bug_id: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id"), nullable=False)
    run_id: Mapped[str | None] = mapped_column(Text, ForeignKey("agent_runs.id"), nullable=True)
    reviewer_role: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    selected_harness: Mapped[str] = mapped_column(Text, nullable=False)
    selected_model: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    secondary_harness: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_effort: Mapped[str] = mapped_column(Text, nullable=False, server_default="max")
    debate_max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    use_resume_when_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BugDebate(Base):
    __tablename__ = "bug_debates"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    bug_id: Mapped[str] = mapped_column(Text, ForeignKey("bugs.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    primary_model: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_model: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    winning_side: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_unresolved: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_final_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BugDebateTurn(Base):
    __tablename__ = "bug_debate_turns"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    debate_id: Mapped[str] = mapped_column(
        Text, ForeignKey("bug_debates.id", ondelete="CASCADE"), nullable=False
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    notes_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
