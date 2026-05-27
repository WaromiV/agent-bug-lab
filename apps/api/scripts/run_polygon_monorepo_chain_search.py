"""
One-shot: fan out 4 parallel searcher runs ON THE MONOREPO (project_000008).

Each run sees:
  - repo_path = data/targets/  (all 6 polygon sub-repos as subdirectories)
  - prepare_dossier             (the recon dossier with 13 hotspots, 9 audits, 4 incidents)
  - prior_bugs                  (all 74 bugs already in the monorepo, with 🆕 markers
                                 distinguishing the latest searcher batch from the originals)
  - cross_repo_chain_emphasis   (extra one-shot hint asking the agent to prioritise
                                 chains that span >1 repo, since that's the unique
                                 value-add of running on the monorepo vs per-repo)

Run from apps/api:  .venv/bin/python -m scripts.run_polygon_monorepo_chain_search
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
NUM_PARALLEL = 4

CHAIN_EMPHASIS = """\
CROSS-REPO CHAIN PRIORITY (for this run only)

You are searching the polygon monorepo at project.repo_path. That directory
contains 6 sub-repositories side-by-side:

  data/targets/bor              — Bor execution client (Go, geth fork)
  data/targets/heimdall-v2      — Heimdall v2 consensus client (Go, Cosmos SDK fork)
  data/targets/cosmos-sdk       — Polygon's Cosmos SDK fork (Go)
  data/targets/cometbft         — Polygon's CometBFT fork (Go)
  data/targets/pos-contracts    — PoS bridge / staking / child-token contracts (Solidity 0.5.x)
  data/targets/sPOL-contracts   — sPOL liquid-staking contracts (Solidity ^0.8)

The point of running on the monorepo (not per-repo) is to find findings
that NO single-repo search could spot:

  • CHAINS that combine a defect in one repo with reachability from another.
    Example shape: a milestone-signature edge case in heimdall-v2 that
    becomes consensus-halting only because bor's checkpoint verifier
    interprets it a specific way; or a state-sync envelope crafted on L1
    pos-contracts that decodes pathologically inside Heimdall's x/clerk
    side-message handler.

  • PROTOCOL-LEVEL invariants violated by sub-system disagreement.
    Example: bor's view of the validator set diverges from heimdall's
    span data because of an asymmetric rounding step in one but not the
    other; or sPOL's L1↔L2 exchange-rate sync trusts a value that the
    bridge predicate computes from a different definition than the sPOL
    controller uses.

  • SECURITY ASSUMPTIONS one component makes that another silently violates.
    Example: cosmos-sdk's x/gov assumes validators behave like the upstream
    Cosmos validator set, but heimdall-v2's x/stake module emits validator
    records with non-cosmos-shaped fields (e.g. the Polygon fork's
    Validator.VotingPower is int64 not math.Int) — bug X in upstream that
    was unreachable becomes reachable under the fork's data shape.

  • PRIOR-BUGS CHAIN EXTENSIONS. The `prior_bugs` array contains 74 bugs
    already filed against this monorepo. Look at which sub-repos a given
    bug touches, then look for an ADJACENT defect in a different sub-repo
    that *amplifies* or *unlocks* the existing one. Cite the source bug id
    explicitly in your description, e.g. "extends bug_NNNNNN by triggering
    its reachability from <other repo's path>".

DO NOT spend tokens on single-repo findings the per-repo passes already
catalogued. We have 74 of those. The unique value here is multi-repo
context. If your finding could have been found by a searcher with access
to only one of the 6 sub-directories, deprioritize it.

The new PRECONDITION VERIFICATION rule still applies — and especially
applies to cross-repo claims, because the data-shape mismatch BETWEEN
sub-repos is where most cross-repo bugs live. Before claiming a chain is
real, verify that the data shape one sub-repo produces is actually what
the other sub-repo consumes.
"""


async def main() -> int:
    cfg = get_settings()

    with SessionLocal() as s:
        monorepo = s.get(Project, MONOREPO_PROJECT_ID)
        if monorepo is None:
            print(f"!! {MONOREPO_PROJECT_ID} not found", file=sys.stderr)
            return 2
        if not monorepo.prepare_dossier:
            print(f"!! {MONOREPO_PROJECT_ID} has no prepare_dossier — run prepare first", file=sys.stderr)
            return 2

        run_settings = settings_service.get_or_init(s)
        spawned: list[str] = []

        for i in range(NUM_PARALLEL):
            run = project_service.enqueue_searcher(
                s,
                project=monorepo,
                harness=run_settings.selected_harness,
                model=run_settings.selected_model,
                effort=run_settings.selected_effort,
                # No dossier/bugs override: enqueue_searcher will auto-load
                # project_000008's own dossier and 74 prior bugs.
            )
            # Inject the chain-emphasis hint as a top-level field. The searcher
            # prompt's _PROMPT_TEMPLATE dumps the whole raw_input as JSON so any
            # top-level key is visible to the agent without prompt changes.
            raw_input = dict(run.raw_input)
            raw_input["cross_repo_chain_emphasis"] = CHAIN_EMPHASIS
            run.raw_input = raw_input
            s.flush()
            spawned.append(run.id)

        s.commit()

    pool = await create_pool(RedisSettings.from_dsn(cfg.redis_url))
    try:
        for run_id in spawned:
            await pool.enqueue_job("run_searcher", run_id)
            print(f"  enqueued {run_id} on {MONOREPO_PROJECT_ID} (monorepo, chain-emphasis)")
    finally:
        await pool.aclose()

    print()
    print(f"fanned out {len(spawned)} parallel monorepo searcher runs")
    print("watch live at  /runs  or  /projects/project_000008")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
