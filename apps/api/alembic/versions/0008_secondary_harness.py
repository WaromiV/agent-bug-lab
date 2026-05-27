"""settings.secondary_harness (per-side harness in debate)

Lets the debate pair pro+judge on one harness and con on another (e.g.
claude_code + codex). Null = fall back to selected_harness.

Revision ID: 0008_secondary_harness
Revises: 0007_static_facts
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_secondary_harness"
down_revision: str | None = "0007_static_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("secondary_harness", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("settings", "secondary_harness")
