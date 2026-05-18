"""scopes table; bugs.scope_id now FKs scopes(id)

Revision ID: 0002_scopes
Revises: 0001_initial
Create Date: 2026-05-17
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_scopes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS scope_id_seq START 1")

    op.create_table(
        "scopes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scopes_project_id", "scopes", ["project_id"])

    # Backfill: every existing project gets a default scope and every existing
    # bug is rewritten to reference that default scope. The old bugs->projects
    # FK must be dropped first so the intermediate UPDATE is allowed.
    op.execute("""
        INSERT INTO scopes (id, project_id, name, description)
        SELECT
            'scope_' || lpad((nextval('scope_id_seq'))::text, 6, '0'),
            p.id,
            p.name,
            'Auto-created during scopes migration; rename freely.'
        FROM projects p;
    """)

    op.drop_constraint("bugs_scope_id_fkey", "bugs", type_="foreignkey")

    op.execute("""
        UPDATE bugs b
        SET scope_id = s.id
        FROM scopes s
        WHERE s.project_id = b.scope_id;
    """)

    op.create_foreign_key(
        "bugs_scope_id_fkey", "bugs", "scopes", ["scope_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("bugs_scope_id_fkey", "bugs", type_="foreignkey")

    # Rewrite each bug.scope_id back to its scope's project_id so the old FK holds.
    op.execute("""
        UPDATE bugs b
        SET scope_id = s.project_id
        FROM scopes s
        WHERE s.id = b.scope_id;
    """)

    op.create_foreign_key(
        "bugs_scope_id_fkey", "bugs", "projects", ["scope_id"], ["id"]
    )

    op.drop_index("ix_scopes_project_id", table_name="scopes")
    op.drop_table("scopes")
    op.execute("DROP SEQUENCE IF EXISTS scope_id_seq")
