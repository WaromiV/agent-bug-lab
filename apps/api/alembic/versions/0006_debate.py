"""debate: wipe critical, add settings.secondary_model + debate_max_rounds,
create bug_debates + bug_debate_turns.

Revision ID: 0006_debate
Revises: 0005_prepare
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0006_debate"
down_revision: str | None = "0005_prepare"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM bug_reviews WHERE reviewer_role = 'critical_thinking_agent'")
    op.execute("DELETE FROM agent_logs WHERE run_id IN (SELECT id FROM agent_runs WHERE role = 'critical_thinking_agent')")
    op.execute("DELETE FROM agent_runs WHERE role = 'critical_thinking_agent'")

    op.execute("CREATE SEQUENCE IF NOT EXISTS debate_id_seq START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS dturn_id_seq START 1")

    op.add_column("settings", sa.Column("secondary_model", sa.Text(), nullable=True))
    op.add_column(
        "settings",
        sa.Column("debate_max_rounds", sa.Integer(), nullable=False, server_default="3"),
    )

    op.create_table(
        "bug_debates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("bug_id", sa.Text(), sa.ForeignKey("bugs.id"), nullable=False),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("primary_model", sa.Text(), nullable=False),
        sa.Column("secondary_model", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("winning_side", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("key_unresolved", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("judge_final_run_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bug_debates_bug_id", "bug_debates", ["bug_id"])
    op.create_index("ix_bug_debates_project_id", "bug_debates", ["project_id"])

    op.create_table(
        "bug_debate_turns",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "debate_id",
            sa.Text(),
            sa.ForeignKey("bug_debates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("notes_md", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_bug_debate_turns_debate_id", "bug_debate_turns", ["debate_id"])


def downgrade() -> None:
    op.drop_index("ix_bug_debate_turns_debate_id", table_name="bug_debate_turns")
    op.drop_table("bug_debate_turns")
    op.drop_index("ix_bug_debates_project_id", table_name="bug_debates")
    op.drop_index("ix_bug_debates_bug_id", table_name="bug_debates")
    op.drop_table("bug_debates")
    op.drop_column("settings", "debate_max_rounds")
    op.drop_column("settings", "secondary_model")
    op.execute("DROP SEQUENCE IF EXISTS dturn_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS debate_id_seq")
