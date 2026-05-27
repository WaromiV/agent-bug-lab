"""projects.static_facts (Solidity static-analysis cache)

Adds a JSONB column for the deterministic static-facts pass that the
prepare worker runs before the LLM step (slither + forge inspect output).

Revision ID: 0007_static_facts
Revises: 0006_debate
Create Date: 2026-05-22
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0007_static_facts"
down_revision: str | None = "0006_debate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("static_facts", JSONB(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "static_facts_generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "static_facts_generated_at")
    op.drop_column("projects", "static_facts")
