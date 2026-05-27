"""bugs.owner_run_id + preliminary scope seed

Revision ID: 0003_scope_ownership
Revises: 0002_scopes
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_scope_ownership"
down_revision: str | None = "0002_scopes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Historical seed list. Auto-seeding has since been removed from the app;
# these rows remain only in databases migrated through this revision.
_PRELIMINARY: list[tuple[str, str, str]] = [
    ("scope_memory_safety",         "Memory safety",         "Buffer overflows, use-after-free, double free, integer overflows, OOB read/write."),
    ("scope_authentication",        "Authentication",        "Authentication boundary issues, credential handling, session establishment."),
    ("scope_authorization",         "Authorization",         "Privilege boundaries, permission checks, capability/role enforcement."),
    ("scope_input_validation",      "Input validation",      "Injection sinks (SQL, command, SSTI), SSRF, deserialization, missing/weak validation."),
    ("scope_cryptography",          "Cryptography",          "Weak / misused / predictable / homegrown crypto, key handling, RNG quality."),
    ("scope_ipc_boundary",          "IPC trust boundary",    "Privilege/process-boundary IPC: parent-trusts-child, validation gaps on IPC messages."),
    ("scope_race_conditions",       "Race conditions",       "TOCTOU, data races, lock ordering, atomicity violations."),
    ("scope_denial_of_service",     "Denial of service",     "Resource exhaustion, unbounded growth, panic / crash paths."),
    ("scope_information_disclosure","Information disclosure","Side channels, error/log leaks, unintended cross-origin exposure."),
    ("scope_supply_chain",          "Supply chain",          "Dependency / build / update / signing / distribution weaknesses."),
    ("scope_logic_flaws",           "Logic flaws",           "Business-logic, state-machine, invariant violations not covered above."),
]


def upgrade() -> None:
    op.add_column(
        "bugs",
        sa.Column("owner_run_id", sa.Text(), sa.ForeignKey("agent_runs.id"), nullable=True),
    )
    op.create_index("ix_bugs_owner_run_id", "bugs", ["owner_run_id"])

    # Seed preliminary scopes for every existing project, idempotently.
    # Scope id = "<seed_id>__<project_id>" so semantic prefixes (e.g.
    # scope_memory_safety) survive while PKs stay globally unique.
    bind = op.get_bind()
    for seed_id, name, description in _PRELIMINARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO scopes (id, project_id, name, description)
                SELECT
                    :seed_id || '__' || p.id,
                    p.id,
                    :name,
                    :description
                FROM projects p
                WHERE NOT EXISTS (
                    SELECT 1 FROM scopes s
                    WHERE s.project_id = p.id AND s.name = :name
                )
                """
            ),
            {"seed_id": seed_id, "name": name, "description": description},
        )


def downgrade() -> None:
    # Remove preliminary scopes by exact name match where no bugs reference them.
    bind = op.get_bind()
    for _seed_id, name, _description in _PRELIMINARY:
        bind.execute(
            sa.text(
                """
                DELETE FROM scopes s
                WHERE s.name = :name
                  AND NOT EXISTS (SELECT 1 FROM bugs b WHERE b.scope_id = s.id)
                """
            ),
            {"name": name},
        )
    op.drop_index("ix_bugs_owner_run_id", table_name="bugs")
    op.drop_column("bugs", "owner_run_id")
