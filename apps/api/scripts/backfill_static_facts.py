"""
One-shot: run the static_facts pass on every Solidity project that doesn't
already have one. Doesn't touch projects.prepare_dossier or run any LLM.

Run from apps/api with:  .venv/bin/python -m scripts.backfill_static_facts

Pass a project_id to force-refresh just one project:
  .venv/bin/python -m scripts.backfill_static_facts project_000004
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from app.db.models import Project
from app.db.session import SessionLocal
from app.services import static_facts


def main(argv: list[str]) -> int:
    target_id = argv[1] if len(argv) > 1 else None

    with SessionLocal() as s:
        if target_id:
            projects = [p for p in [s.get(Project, target_id)] if p is not None]
            if not projects:
                print(f"project {target_id} not found")
                return 1
        else:
            projects = list(s.query(Project).all())

    for project in projects:
        already = (
            project.static_facts is not None
            and project.static_facts_generated_at is not None
        )
        if already and not target_id:
            print(f"{project.id} {project.name}: already has facts, skipping")
            continue

        repo_path = Path(project.repo_path)
        if not static_facts.is_solidity_target(repo_path):
            print(f"{project.id} {project.name}: not a Solidity target, skipping")
            continue

        print(f"--- {project.id} {project.name} ---")
        print(f"  repo_path={repo_path}")
        try:
            facts = static_facts.collect(project.id, repo_path)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}")
            continue

        with SessionLocal() as s:
            p = s.get(Project, project.id)
            if p is None:
                print(f"  vanished, skipping")
                continue
            p.static_facts = facts
            p.static_facts_generated_at = datetime.now(timezone.utc)
            s.commit()

        stats = facts.get("stats", {})
        errs = len(facts.get("errors", []))
        print(
            f"  done: build_ok={facts.get('build_ok')} "
            f"contracts={stats.get('user_contracts')} "
            f"ext_fns={stats.get('external_functions')} "
            f"edges={stats.get('callgraph_edges')} "
            f"errors={errs}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
