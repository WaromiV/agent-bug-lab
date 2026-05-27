"""settings.selected_effort + agent_runs.effort

Revision ID: 0004_effort
Revises: 0003_scope_ownership
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_effort"
down_revision: str | None = "0003_scope_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Global default reasoning-effort setting, snapshotted onto each run row
    # when it's queued — so a settings change after queue time doesn't
    # silently retro-apply.
    op.add_column(
        "settings",
        sa.Column(
            "selected_effort",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'max'"),
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("effort", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "effort")
    op.drop_column("settings", "selected_effort")
