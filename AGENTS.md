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
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8001 &
arq app.workers.arq_settings.WorkerSettings &
cd ../web && npm install && npm run dev
```

Then open http://127.0.0.1:5173, create a project pointing at any read-only
repo (set `FIXED_REPO_ROOT` first), and watch the searcher run live.

## What's not here yet

- Cloud-hosted multi-tenant variant — see [`SPEC.md`](./SPEC.md) §23 for the explicit non-goals.
- CI pipelines for backend + frontend (ruff, alembic dry-run, tsc).
- Automatic bounty submission — agents will never file reports for you.
- Source modification by agents — forbidden by design. The target repo is
  always mounted read-only.
