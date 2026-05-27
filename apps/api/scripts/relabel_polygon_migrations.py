"""
One-shot: clean up the ugly `[migrated_from:bug_NNNNNN] (from ...)` prefix on
project_000008 bug descriptions.

  · Old batch (source id ≤ 56): strip the prefix entirely.
  · New batch from the 4 parallel searcher fanout (source id ≥ 133): replace
    the prefix with a compact "🆕 [NEW · polygon-<repo>] " marker so the
    user can scan for fresh findings.

Idempotent: re-running finds nothing to change because the cleaned/relabelled
descriptions no longer match the original prefix pattern.

Run from apps/api:  .venv/bin/python -m scripts.relabel_polygon_migrations
"""
from __future__ import annotations

import re

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models import Bug, Scope

TARGET_PROJECT_ID = "project_000008"
NEW_BATCH_SOURCE_THRESHOLD = 100  # safely between old (≤56) and new (≥133)

_PREFIX_RE = re.compile(
    r"^\[migrated_from:bug_(\d{6})\] \(from ([^)]+)\)\n\n",
    re.S,
)


def main() -> int:
    with SessionLocal() as s:
        rows = s.execute(
            select(Bug)
            .join(Scope, Bug.scope_id == Scope.id)
            .where(Scope.project_id == TARGET_PROJECT_ID)
        ).scalars().all()

        stripped = 0
        relabelled = 0
        skipped = 0
        for b in rows:
            desc = b.description or ""
            m = _PREFIX_RE.match(desc)
            if not m:
                skipped += 1
                continue
            src_n = int(m.group(1))
            src_label = m.group(2).strip()
            body = desc[m.end():]
            if src_n >= NEW_BATCH_SOURCE_THRESHOLD:
                b.description = f"🆕 [NEW · {src_label}] {body}"
                relabelled += 1
            else:
                b.description = body
                stripped += 1
        s.commit()

    print(f"stripped old-batch prefix: {stripped}")
    print(f"relabelled new-batch prefix: {relabelled}")
    print(f"skipped (no prefix found): {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
