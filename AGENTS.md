# agent-bug-lab — design notes for contributors & agents

This file is the institutional memory of the codebase. Read it before adding
features or proposing refactors. The product spec is in [`SPEC.md`](./SPEC.md);
this file is the *how* and *why*.

## Shape

- `apps/api/` — FastAPI backend + Arq workers (Python 3.13)
- `apps/web/` — React + Vite frontend
- `packages/shared/schemas/` — Draft 2020-12 JSON schemas shared between agents and backend
- `data/` — run artifacts (gitignored)

## Design constraints (don't violate without good reason)

1. **One harness runner.** `app/services/harness_runner.py::HarnessSpec` is an
   ABC; `CodexSpec` and `ClaudeCodeSpec` are concrete subclasses. They own
   `build_argv`, `build_stdin`, `extract_output`. Adding a new harness ==
   new subclass + entry in `HARNESS_REGISTRY`. Nothing else changes (OCP).

2. **One run-lifecycle driver.** `app/workers/runner.py::drive_run` is the
   single place that moves a run through `queued → running → succeeded|failed`
   and persists artifacts. The three workers (searcher / cleaner / critical)
   are 4-line shims that pass a role-specific `apply_output` callback.

3. **Pydantic models *are* the validators.** `BugContract` in
   `app/schemas/bug.py` is the single source of truth for what a bug looks
   like on the wire. SQLAlchemy mirrors the same 7 fields verbatim.

4. **Agent prompts live in one place.** `app/services/prompts.py` holds the
   full objective text for every role. Edit the prompt there, not in the
   input builders.

5. **The DB is the source of truth; `data/` is the forensic trail.** Every
   important run gets its own `data/<role>_<id>/` directory with the harness
   command, the input JSON, the raw output JSON, stdout/stderr, and a
   role-specific summary (`validated_bugs.json`, `kept_bugs.json`, etc.).

## Scope model (this is the killer feature)

A *scope* is a research-direction grouping — "memory safety", "IPC trust
boundary", "race conditions" — **not** a bounty-program target list.

- Every project is seeded with 11 preliminary scopes (see
  `scope_service.PRELIMINARY_SCOPES`). These persist forever; nobody deletes
  scopes. The migration `0003_scope_ownership.py` ensures existing projects
  also get the preliminary set.
- Agents may **create** new scopes, **rename** existing ones, and **retag**
  bugs they themselves produced (the `bugs.owner_run_id` column tracks
  ownership). The runtime silently drops retag attempts for bugs the agent
  doesn't own and ignores any `delete` entries — these aren't errors, just
  no-ops.
- The agent contract carries this via an optional `scope_ops` block in
  output: `{ create: [...], rename: [...] }`. Bugs may freely reference
  newly-created scope ids in the same response.

## Harness invocation, real shapes

The spec sketched `<bin> --model X < input.json`. Real CLIs have different
ergonomics; the `HarnessSpec` subclasses adapt:

- **Codex** — `codex exec --skip-git-repo-check --sandbox read-only -m <model> -o <data_dir>/codex_last_message.txt -` and pipes a *prompt* (wrapped JSON) to stdin. Resume = `codex exec resume <session_id> …`.
- **Claude Code** — `claude -p --model <model> --output-format json --permission-mode bypassPermissions` with the prompt on stdin. Resume = append `--resume <session_id>`. The JSON envelope returns `result` (model text) and `session_id`, which we lift into the parsed payload so `--resume` "just works".

Both CLIs read a *prompt* (a string), not a JSON object. `build_prompt()` in
`harness_runner.py` wraps the JSON payload in instructions that force the
model to emit JSON-only output.

## Live WebSocket

`GET /api/runs/{id}/ws` pushes:

- `{ kind: "run", run: RunRead }` — full run snapshot, on connect + on change.
- `{ kind: "log", row: LogRead }` — one new log row.
- `{ kind: "tick", now: ISO }` — 1 Hz heartbeat.
- `{ kind: "end", status }` — terminal frame; server closes.
- `{ kind: "error", error }` — fatal error.

The frontend `useRunStream` hook owns the socket for an entire run-detail
page. A local 1 Hz interval also bumps a tick state while the run is
running, so the displayed duration ticks even when the server has nothing
new to say.

## Gotchas

- **Use `127.0.0.1` in DATABASE_URL**, not `localhost`. On some hosts
  (mixed nsswitch / IPv6 setups), psycopg without a `connect_timeout` can
  hang during SQLAlchemy `engine.connect()`. The default `.env.example`
  reflects this.
- **Project / run / scope / bug ids** come from Postgres sequences via
  `app/core/ids.py::next_id(kind)`. They look like `project_000001`,
  `run_000042`, `bug_000123`. Scope ids may also include a `__<project>`
  suffix for human-readable semantic prefixes (`scope_memory_safety__project_000007`).
- **Bug ids from agents are advisory.** The ingest layer always rewrites
  `bugs.id` from `bug_id_seq` to guarantee uniqueness across runs.
- **`harness_session_id`** is captured from harness output (Claude provides
  one in its JSON envelope; Codex does not currently). It's used when the
  user hits "Resume" on a finished searcher run.
- **Scope deletion is forbidden, even via the API.** The DELETE route was
  intentionally removed; scopes accumulate as audit-trail vocabulary.

## Verifying locally end-to-end

```bash
# Start postgres + redis (Docker or local services)
cd apps/api
docker compose up -d postgres redis
alembic upgrade head
nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --app-dir . > /tmp/abl-api.log 2>&1 & disown
nohup .venv/bin/arq app.workers.arq_settings.WorkerSettings > /tmp/abl-arq.log 2>&1 & disown
cd ../web && npm run dev
```

Then open http://127.0.0.1:5173, create a project pointing at any read-only
repo (set `FIXED_REPO_ROOT` first), and watch the searcher run live.

## How to operate the system (for Claude / the operator)

### Starting the stack
Services die frequently (docker stops, machine sleeps). Always check
before doing anything:
```bash
ss -tlnp | grep -E ":8001|:5435|:6380|:5173"
```
If any are missing:
```bash
docker compose up -d postgres redis          # DB + queue
cd apps/api
nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --app-dir . > /tmp/abl-api.log 2>&1 & disown
nohup .venv/bin/arq app.workers.arq_settings.WorkerSettings > /tmp/abl-arq.log 2>&1 & disown
cd ../web && nohup npm run dev > /tmp/abl-web.log 2>&1 & disown
```
After code changes to prompts/services/workers, restart API + arq
(they don't auto-reload).

### Creating a project
Via API:
```bash
curl -s -X POST http://localhost:8001/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"<name>","bug_bounty_url":"https://immunefi.com/bug-bounty/<slug>/scope","repo_path":"<path>"}'
```
This auto-queues a prepare run. If the URL is Immunefi, the scope
scraper auto-runs (if playwright is installed) to seed severity_tiers
and out_of_scope into the dossier.

### Queuing searcher runs
For a quick batch:
```python
# In a .venv/bin/python script from apps/api/
import asyncio
from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import get_settings
from app.core.ids import next_id
from app.db.models import Project
from app.db.session import SessionLocal
from app.services import project_service, settings_service, scope_service, run_manager

STEERING = '''<focus instructions here>'''

async def main():
    cfg = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(cfg.redis_url))
    with SessionLocal() as s:
        project = s.get(Project, '<project_id>')
        rs = settings_service.get_or_init(s)
        scopes = scope_service.list_for_project(s, project.id)
        wrapper = project.prepare_dossier
        dossier = wrapper.get('dossier') if isinstance(wrapper, dict) else None
        prior_bugs = project_service._load_prior_bugs(s, project.id)
        for i in range(N):
            run_id = next_id(s, 'run')
            raw_input = project_service._build_searcher_input(
                task_id=run_id, project=project, scopes=scopes,
                min_findings=0, max_findings=5,
                prepare_dossier=dossier, prior_bugs=prior_bugs,
                static_facts_summary=None,
            )
            raw_input['focus_instructions'] = STEERING
            raw_input['constraints']['min_findings'] = 0
            run = run_manager.create_run(
                s, project_id=project.id, role='searcher_agent',
                harness=rs.selected_harness, model=rs.selected_model,
                effort=rs.selected_effort, objective=raw_input['objective'],
                raw_input=raw_input, run_id=run_id,
            )
        s.commit()
        # Enqueue all
        from sqlalchemy import select
        from app.db.models import AgentRun
        runs = list(s.execute(
            select(AgentRun).where(AgentRun.project_id=='<project_id>')
            .where(AgentRun.status=='queued')
            .order_by(AgentRun.created_at.desc()).limit(N)
        ).scalars())
        for r in runs:
            await pool.enqueue_job('run_searcher', r.id)
    await pool.aclose()
asyncio.run(main())
```

### Queuing a debate
Via API:
```bash
curl -s -X POST http://localhost:8001/api/bugs/<bug_id>/debate \
  -H 'Content-Type: application/json' -d '{}'
```
Debate uses settings.selected_harness/model for pro+judge, and
settings.secondary_harness/model for con. Set via:
```bash
curl -s -X PATCH http://localhost:8001/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"secondary_harness":"codex","secondary_model":"gpt-5.5-codex"}'
```

### Checking run status
```python
from app.db.session import SessionLocal
from app.db.models import AgentRun, Bug
with SessionLocal() as s:
    r = s.get(AgentRun, 'run_XXXXXX')
    print(f'{r.id}: {r.status} err={r.error}')
```

### Reading bugs
```python
from app.db.session import SessionLocal
from app.db.models import Bug, Scope
from sqlalchemy import select
with SessionLocal() as s:
    rows = list(s.execute(
        select(Bug, Scope.name).join(Scope, Bug.scope_id == Scope.id)
        .where(Scope.project_id == '<project_id>')
        .where(Bug.severity.in_(['critical','high','medium']))
        .order_by(Bug.id)
    ).all())
    for b, sn in rows:
        print(f'{b.id} [{b.severity}] {b.description[:120]}')
```

### Updating a bug (kill/downgrade)
```python
with SessionLocal() as s:
    b = s.get(Bug, 'bug_XXXXXX')
    b.severity = 'low'
    b.description = '[KILLED — reason] ' + b.description
    s.commit()
```

### Backfilling static_facts
```bash
cd apps/api
.venv/bin/python -m scripts.backfill_static_facts <project_id>
```

### Monitoring runs
Use the Monitor tool with a polling script:
```bash
while true; do
  .venv/bin/python -c "
from app.db.session import SessionLocal
from app.db.models import AgentRun, Bug
from sqlalchemy import select
with SessionLocal() as s:
    for rid in ('run_X','run_Y','run_Z'):
        r = s.get(AgentRun, rid)
        print(f'{r.id}: {r.status}')
    bugs = list(s.execute(select(Bug).where(
        Bug.owner_run_id.in_(['run_X','run_Y','run_Z'])
    ).order_by(Bug.id)).scalars())
    print(f'BUGS: {len(bugs)}')
    for b in bugs:
        print(f'  {b.id} [{b.severity}] {b.description[:100]}')
    if all done: print('ALL DONE')
"
  sleep 60
done
```

### RPC checks (mandatory before claiming severity)
```bash
# Ethereum
cast balance <addr> --rpc-url https://ethereum-rpc.publicnode.com --ether
cast call <addr> "<sig>" <args> --rpc-url https://ethereum-rpc.publicnode.com

# Stacks
curl -s "https://api.mainnet.hiro.so/v2/pox"

# Arbitrum
cast call <addr> "<sig>" <args> --rpc-url https://arbitrum-one-rpc.publicnode.com
```

### Scope scraping (Immunefi)
Via Playwright MCP tools in conversation:
```
mcp__playwright__browser_navigate → https://immunefi.com/bug-bounty/<slug>/scope
mcp__playwright__browser_evaluate → JS_EXTRACT_ALL (from scope_scraper.py)
```
Or standalone (needs playwright installed):
```bash
cd apps/api
.venv/bin/python -m app.services.scope_scraper <slug>
```

### GitHub duplicate checks (mandatory before investing in a bug)
```bash
gh issue list --repo <org>/<repo> --search "<keywords>" --state all --limit 20
gh pr list --repo <org>/<repo> --search "<keywords>" --state all --limit 20
```

### Sending Telegram notifications
```bash
curl -sf -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d chat_id="<CHAT_ID>" -d parse_mode="HTML" -d text="<message>"
```

## What's not here yet

- Cloud-hosted multi-tenant variant — see [`SPEC.md`](./SPEC.md) §23 for the explicit non-goals.
- CI pipelines for backend + frontend (ruff, alembic dry-run, tsc).
- Automatic bounty submission — agents will never file reports for you.
- Source modification by agents — forbidden by design. The target repo is
  always mounted read-only.

---

# Bug Bounty Research Operating Manual

## Golden rule

**A code bug is not a finding. A finding is a code bug that enables
an impact the target cannot already achieve at similar cost without
the bug.**

Before investing ANY effort into a candidate bug:
> "Can the same impact be achieved WITHOUT this bug? At what cost?"

If yes at similar cost — kill immediately. Do not PoC. Do not debate.

---

## Pre-engagement checklist (BEFORE running agents)

### 1. Read the scope page with Playwright
```
mcp__playwright__browser_navigate → https://immunefi.com/bug-bounty/<target>/scope
mcp__playwright__browser_snapshot → extract ALL content
```
Extract verbatim:
- Every severity qualifier (per asset class separately)
- Every out-of-scope clause
- Max payout per tier
- Program-specific rules

Also read the information page:
```
mcp__playwright__browser_navigate → https://immunefi.com/bug-bounty/<target>/information
```
Extract: reward structure, team's prioritized attack vectors, special
rules, deposit requirements.

Do NOT rely on memory of "what programs usually say." Open. Read. Save.

### 2. Count the bountiable qualifiers
If ≤3 qualifiers for the target asset class → surface is narrow. Steer
agents at ONLY those surfaces. Don't run generic prompts.

### 3. Download and search ALL audit PDFs
```bash
curl -sL "<pdf_url>" -o audit.pdf
pdftotext audit.pdf - | grep -i "<mechanism keywords>"
```
If an audit already covers the mechanism class → likely dead.

### 4. Check GitHub issues and PRs FIRST
BEFORE any deep analysis — this takes 30 seconds and kills 50% of
candidates:
```bash
gh issue list --repo <org>/<repo> --search "<keywords>" --state all --limit 20
gh pr list --repo <org>/<repo> --search "<keywords>" --state all --limit 20
```
If team already filed/discussed/fixed → dead. Only exception: "materially
higher severity or novel exploit path" — must state explicitly.

---

## Kill-tests (ALL must pass before PoC investment)

### Kill-test 1: Baseline comparison
"Can the same impact happen without this bug?"
- Block stuffing → compute cost with plain transfers
- DoS → compute equivalent DoS cost without the bug
- Fund loss → does attack require already-achievable conditions?

If bug gives < 10x improvement over baseline → kill.

### Kill-test 2: Deployment status
```bash
cast call <addr> "<function>(uint32)(address)" <id> --rpc-url <rpc>
```
Undeployed feature/game-type/migration → info at best. Stop.

### Kill-test 3: Known issue check (GitHub)
```bash
gh issue list --repo <org>/<repo> --search "<keywords>" --state all
gh search code "<function_name> repo:<org>/<repo>"
```
Closed issue or merged PR with the same mechanism → dead.

### Kill-test 4: Scope match
Does impact match a SPECIFIC qualifier VERBATIM? If you have to stretch
the language → likely dead.

### Kill-test 5: Exclusion check
Read every out-of-scope clause. Common killers:
- "attacks requiring access to privileged addresses"
- "findings already public or known"
- "attacks on 3rd party services including AWS"
- specific binary names excluded as event observers
- "DoS without fund loss capped at $X"

---

## Searcher agent steering

### DO
- `min_findings=0` — empty > padding
- Include `focus_instructions` with exact severity qualifiers + SKIP list
- Pass `prepare_dossier` with `severity_tiers` and `out_of_scope`
- Pass `prior_bugs` so agents don't re-report

### DON'T
- Generic "find bugs" prompts
- High `min_findings` — agents pad with garbage
- `--resume` — stale context (disabled globally)
- Queue >5 agents without checking first-batch results

### After each batch
1. Read every medium+ `missing_for_full_chain`
2. Run kill-tests 1-5
3. Kill dead findings in DB immediately
4. Then decide whether to queue more

---

## RPC verification (mandatory)

Every on-chain impact claim needs:
```bash
cast balance <addr> --rpc-url <rpc> --ether          # funds at risk
cast call <addr> "<sig>" <args> --rpc-url <rpc>       # deployment status
curl -s "https://api.mainnet.hiro.so/v2/pox"          # Stacks-specific
```

Public RPCs:
- Ethereum: https://ethereum-rpc.publicnode.com
- Optimism: https://optimism-rpc.publicnode.com
- Stacks: https://api.mainnet.hiro.so
- Polygon: https://polygon-bor-rpc.publicnode.com

---

## Filing decision (ALL 7 must be YES)

1. Mechanism verified? (source + local PoC)
2. Mainnet confirmed? (RPC: feature deployed + funds at risk)
3. No duplicates? (GitHub issues + PRs + audit PDFs)
4. Scope match? (specific qualifier verbatim)
5. No exclusions? (every clause checked)
6. Baseline comparison? (attack NOT achievable at similar cost without bug)
7. Would the team be surprised? (not a known/accepted risk)

---

## Lessons learned (2026-05-24)

### Optimism ($2M bounty) — 31 bugs, 0 bountiable
- All findings hit bond carve-outs or undeployed features
- Only 3 severity qualifiers — should have recognized before 16 agent runs
- ETHLockbox ($450M) best finding but gated on undeployed multi-portal

### Stacks ($250K bounty) — 44 bugs, 0 filable
- Multisig encoding mismatch (HIGH): GitHub #1694 already known. Wasted
  hours before checking.
- Cost underpricing (MEDIUM): PoC'd, mainnet-confirmed, then discovered
  plain transfers stuff blocks for $700/day regardless. Bug gives 35%
  discount on an already-trivial attack. Team already discusses this in
  issues #4189 and #5398.
- Signer bugs: scope explicitly excludes stacks-signer binary.

### Errors to avoid (documented from real incidents)

1. **Skipping baseline comparison.** Before investing in a PoC, check
   whether the same impact is achievable without the bug at similar
   cost. If it is, the bug has no marginal value. This is now enforced
   in agent prompts (IMPACT_VERIFICATION_BLOCK) but the human operator
   must also verify it — agents can miss it.

2. **Building PoC before kill-tests.** A 30-second `gh issue list`
   can kill a finding before hours are spent on source verification,
   RPC checks, and debates. Always run kill-tests first.

3. **Changing assessment without new evidence.** Once a finding fails
   a kill-test, mark it dead in the DB and stop. Do not revisit unless
   genuinely new evidence appears. Sunk cost is not evidence.

4. **Continuing analysis after disqualifying evidence.** When a GitHub
   issue or merged PR covers the same mechanism, the finding is dead.
   Do not argue "the issue might not cover this specific variant"
   without concrete proof of a novel escalation path.

5. **Relying on trained knowledge instead of reading the scope page.**
   Open the scope page in Playwright and read the actual text. Do not
   reason from "what bounty programs usually say." This applies to
   both the agent (now enforced via BOUNTY_SCOPE_BLOCK) and the
   operator.

6. **Not verifying arithmetic against on-chain data.** When computing
   attack economics, verify every assumption (block time, budget
   scope, fee structure) against the actual chain. A 120x error in
   block counting produces a 120x error in cost estimates.

7. **Running many agents before reading the scope.** Count the
   bountiable severity qualifiers before queuing agents. If the
   program has ≤3 qualifiers, the attack surface is narrow. Steer
   agents explicitly; do not run generic prompts.
