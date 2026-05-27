"""projects.prepare_dossier + projects.prepare_run_id

Revision ID: 0005_prepare
Revises: 0004_effort
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0005_prepare"
down_revision: str | None = "0004_effort"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("prepare_dossier", JSONB(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("prepare_run_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "prepare_run_id")
    op.drop_column("projects", "prepare_dossier")
