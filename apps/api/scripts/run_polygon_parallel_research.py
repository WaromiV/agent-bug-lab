"""
One-shot: fan out 4 parallel searcher runs across the top-4 polygon source
repos, each enriched with the monorepo dossier + every prior polygon bug.

Top-4 picked by descending `score` on `project_000008.prepare_dossier`'s
`candidate_hotspots`:
  pos-contracts  (RootChainManager 0.87)
  heimdall-v2    (x/checkpoint     0.82)
  sPOL-contracts (Ethereum side    0.80)
  bor            (bor consensus    0.78)

Run from apps/api with: .venv/bin/python -m scripts.run_polygon_parallel_research
"""
from __future__ import annotations

import asyncio
import sys

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.db.models import Project
from app.db.session import SessionLocal
from app.services import project_service, settings_service

MONOREPO_PROJECT_ID = "project_000008"

# project_id → friendly label for log lines
FANOUT_TARGETS: list[tuple[str, str]] = [
    ("project_000005", "polygon-pos-contracts"),  # 0.87
    ("project_000002", "polygon-heimdall-v2"),    # 0.82
    ("project_000004", "polygon-sPOL-contracts"), # 0.80
    ("project_000001", "polygon-bor"),            # 0.78
]


async def main() -> int:
    cfg = get_settings()

    with SessionLocal() as s:
        monorepo = s.get(Project, MONOREPO_PROJECT_ID)
        if monorepo is None or not monorepo.prepare_dossier:
            print(f"!! {MONOREPO_PROJECT_ID} has no prepare_dossier", file=sys.stderr)
            return 2
        wrapper = monorepo.prepare_dossier
        dossier = wrapper.get("dossier") if isinstance(wrapper, dict) else None
        if not dossier:
            print("!! prepare_dossier.dossier is empty", file=sys.stderr)
            return 2

        prior_bugs = project_service._load_prior_bugs(s, MONOREPO_PROJECT_ID)
        print(
            f"loaded monorepo dossier ({len(dossier.get('candidate_hotspots', []))} hotspots) "
            f"+ {len(prior_bugs)} prior bugs from {MONOREPO_PROJECT_ID}"
        )

        run_settings = settings_service.get_or_init(s)
        spawned: list[tuple[str, str, str]] = []  # (project_id, label, run_id)

        for pid, label in FANOUT_TARGETS:
            project = s.get(Project, pid)
            if project is None:
                print(f"  WARN: {pid} ({label}) not found, skipping")
                continue
            run = project_service.enqueue_searcher(
                s,
                project=project,
                harness=run_settings.selected_harness,
                model=run_settings.selected_model,
                effort=run_settings.selected_effort,
                dossier_override=dossier,
                prior_bugs_override=prior_bugs,
            )
            spawned.append((pid, label, run.id))
        s.commit()

    if not spawned:
        print("!! no runs spawned", file=sys.stderr)
        return 2

    pool = await create_pool(RedisSettings.from_dsn(cfg.redis_url))
    try:
        for pid, label, run_id in spawned:
            await pool.enqueue_job("run_searcher", run_id)
            print(f"  enqueued {run_id} on {pid} ({label})")
    finally:
        await pool.close()

    print()
    print(f"fanned out {len(spawned)} parallel searcher runs")
    print("watch them at /runs in the UI, or poll /api/runs/<id>")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
