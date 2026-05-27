"""
One-shot: copy every bug from the six polygon source projects into the new
polygon monorepo project (project_000008). The source projects are left
untouched so we keep the audit history of which sub-target each bug came
from.

Run from apps/api with: .venv/bin/python -m scripts.migrate_polygon_bugs

Idempotency: tracks migrated bug ids by composing a marker on owner_run_id +
scope name + description prefix. If you re-run, bugs whose (source bug id)
already appears as a "migrated_from:" line in a target description are
skipped.
"""
from __future__ import annotations

import re
import sys

from sqlalchemy import select

from app.core.ids import next_id
from app.db.models import Bug, Project, Scope
from app.db.session import SessionLocal

SOURCE_PROJECT_IDS = [
    "project_000001",  # polygon-bor
    "project_000002",  # polygon-heimdall-v2
    "project_000003",  # polygon-cosmos-sdk
    "project_000004",  # polygon-sPOL-contracts
    "project_000005",  # polygon-pos-contracts
    "project_000006",  # polygon-cometbft
]
TARGET_PROJECT_ID = "project_000008"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("_", name.lower()).strip("_")


def main() -> int:
    with SessionLocal() as s:
        target = s.get(Project, TARGET_PROJECT_ID)
        if target is None:
            print(f"!! target {TARGET_PROJECT_ID} not found", file=sys.stderr)
            return 2

        # Index existing target scopes by exact name so we coalesce instead of
        # creating duplicates if the script runs more than once.
        target_scopes_by_name: dict[str, Scope] = {
            sc.name: sc
            for sc in s.execute(
                select(Scope).where(Scope.project_id == TARGET_PROJECT_ID)
            ).scalars()
        }

        # Track which source bug ids we've already copied into the target so
        # re-runs are a no-op.
        existing_migrations: set[str] = set()
        for desc in s.execute(
            select(Bug.description)
            .join(Scope, Bug.scope_id == Scope.id)
            .where(Scope.project_id == TARGET_PROJECT_ID)
        ).scalars():
            m = re.match(r"\[migrated_from:(bug_\d{6})\]", desc or "")
            if m:
                existing_migrations.add(m.group(1))

        total = 0
        skipped = 0
        per_source: dict[str, int] = {}

        for src_pid in SOURCE_PROJECT_IDS:
            src_project = s.get(Project, src_pid)
            if src_project is None:
                print(f"  WARN: source {src_pid} not found, skipping")
                continue
            rows = s.execute(
                select(Bug, Scope)
                .join(Scope, Bug.scope_id == Scope.id)
                .where(Scope.project_id == src_pid)
            ).all()

            for bug, src_scope in rows:
                if bug.id in existing_migrations:
                    skipped += 1
                    continue

                # Find or create matching scope on the target by name.
                tgt_scope = target_scopes_by_name.get(src_scope.name)
                if tgt_scope is None:
                    new_scope_id = (
                        f"scope_{slugify(src_scope.name)}__{TARGET_PROJECT_ID}"
                    )
                    if s.get(Scope, new_scope_id) is not None:
                        # Collide-safe fallback: append a counter.
                        n = 2
                        while s.get(Scope, f"{new_scope_id}_{n}") is not None:
                            n += 1
                        new_scope_id = f"{new_scope_id}_{n}"
                    tgt_scope = Scope(
                        id=new_scope_id,
                        project_id=TARGET_PROJECT_ID,
                        name=src_scope.name,
                        description=src_scope.description,
                    )
                    s.add(tgt_scope)
                    s.flush()
                    target_scopes_by_name[src_scope.name] = tgt_scope

                # Insert the copy. The "[migrated_from:bug_NNNNNN] (from
                # <source project name>)" prefix preserves provenance for
                # humans reading the description and gives the idempotency
                # marker a stable place to live.
                new_bug_id = next_id(s, "bug")
                provenance = (
                    f"[migrated_from:{bug.id}] (from {src_project.name})\n\n"
                )
                new_bug = Bug(
                    id=new_bug_id,
                    severity=bug.severity,
                    scope_id=tgt_scope.id,
                    description=provenance + bug.description,
                    repro_path=bug.repro_path,
                    repro_usage=bug.repro_usage,
                    missing_for_full_chain=bug.missing_for_full_chain,
                    # owner_run_id stays None so cleaner/critical agents won't
                    # try to retag migrated bugs (they weren't produced by an
                    # agent run that ran against this monorepo project).
                    owner_run_id=None,
                )
                s.add(new_bug)
                total += 1
                per_source[src_pid] = per_source.get(src_pid, 0) + 1

        s.commit()

    print(f"copied {total} bugs into {TARGET_PROJECT_ID}, skipped {skipped} already migrated")
    for src_pid in SOURCE_PROJECT_IDS:
        print(f"  · {src_pid}: {per_source.get(src_pid, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
