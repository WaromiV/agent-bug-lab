"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-17
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS project_id_seq START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS run_id_seq START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS bug_id_seq START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS review_id_seq START 1")

    op.create_table(
        "projects",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("bug_bounty_url", sa.Text(), nullable=False),
        sa.Column("repo_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "bugs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("repro_path", sa.Text(), nullable=False),
        sa.Column("repro_usage", sa.Text(), nullable=False),
        sa.Column("missing_for_full_chain", sa.Text(), nullable=False),
    )
    op.create_index("ix_bugs_scope_id", "bugs", ["scope_id"])
    op.create_index("ix_bugs_severity", "bugs", ["severity"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("harness", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("resume_from_run_id", sa.Text(), nullable=True),
        sa.Column("harness_session_id", sa.Text(), nullable=True),
        sa.Column("data_dir", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_input", JSONB(), nullable=False),
        sa.Column("raw_output", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_role", "agent_runs", ["role"])

    op.create_table(
        "agent_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_logs_run_id", "agent_logs", ["run_id"])

    op.create_table(
        "bug_reviews",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("bug_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("reviewer_role", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bug_reviews_bug_id", "bug_reviews", ["bug_id"])
    op.create_index("ix_bug_reviews_project_id", "bug_reviews", ["project_id"])
    op.create_index("ix_bug_reviews_created_at", "bug_reviews", ["created_at"])

    op.create_table(
        "settings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("selected_harness", sa.Text(), nullable=False),
        sa.Column("selected_model", sa.Text(), nullable=False),
        sa.Column("use_resume_when_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index("ix_bug_reviews_created_at", table_name="bug_reviews")
    op.drop_index("ix_bug_reviews_project_id", table_name="bug_reviews")
    op.drop_index("ix_bug_reviews_bug_id", table_name="bug_reviews")
    op.drop_table("bug_reviews")
    op.drop_index("ix_agent_logs_run_id", table_name="agent_logs")
    op.drop_table("agent_logs")
    op.drop_index("ix_agent_runs_role", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_project_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_bugs_severity", table_name="bugs")
    op.drop_index("ix_bugs_scope_id", table_name="bugs")
    op.drop_table("bugs")
    op.drop_table("projects")
    op.execute("DROP SEQUENCE IF EXISTS review_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS bug_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS run_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS project_id_seq")
