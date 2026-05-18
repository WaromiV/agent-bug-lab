# Agentic Bug Research Monorepo Development Spec

## 1. Goal

Build a clean, observable web application for running security research agents against arbitrary codebases.

The system must:

- register projects
- attach a bug bounty / audit scope link to each project
- automatically start a searcher run when a project is created
- launch agent runs through Codex CLI, Claude Code CLI, or compatible raw JSON harnesses
- support `--resume` for Codex / Claude Code harnesses when continuing an existing agent session
- pass the model from a settings panel into the selected harness using `--model`
- analyze a local repository at a fixed configured location in read-only mode
- collect 1 to 5 candidate bugs per searcher run
- store all candidate bugs, including weak, incomplete, duplicate, or not-yet-filable findings
- expose projects, runs, logs, bugs, review queues, and cleanup status in a web UI
- support cleaner agents that find and remove bad bug entries
- support critical-thinking agents that refine promising findings
- stay target-agnostic

This is a **Python FastAPI + React monorepo**.

---

## 2. Critical Core Concepts

### `searcher-agent`

Finds candidate bugs.

- starts automatically when a project is created
- analyzes the project repository in read-only mode
- returns 1 to 5 findings per run
- must output strict JSON
- must never modify the target repository
- stores all findings, even if incomplete or not filable yet

### `cleaner-agent`

Removes weak bugs from the database.

- runs against a selected group of bugs from the review queue
- identifies hallucinated, duplicate, weak, non-security, or non-actionable findings
- deletes bad bug rows from the bugs table
- writes a cleanup artifact directory under `data/cleaner_<review_id>`
- must explain what it removed and why in review artifacts

### `critical-thinking-agent`

Attacks the best findings.

- checks exploitability
- challenges attacker assumptions
- improves description, repro_usage, and missing_for_full_chain
- does not delete bugs unless explicitly running in cleaner mode

---

## 3. Core Product Flow

```
project created → searcher auto-runs → 1..5 candidate bugs stored →
review queue surfaces stale/unreviewed bugs → cleaner-agent removes weak bugs →
critical-thinking-agent refines surviving bugs.
```

---

## 4. Monorepo Layout

```
agent-bug-lab/
├── apps/
│   ├── api/                FastAPI backend
│   └── web/                React frontend
├── packages/shared/schemas Shared JSON schemas
├── data/                   Run artifacts
├── docker-compose.yml
├── README.md
└── .env.example
```

(See section 4 of the original spec for the full directory tree — all paths preserved.)

---

## 5. Backend Stack

Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic v2, Redis, Arq, structlog.

PostgreSQL is the source of truth. Redis is for background queues, temporary run state, and live log pub/sub. The source repository is mounted read-only into the backend container.

---

## 6. Frontend Stack

React, TypeScript, Vite, TanStack Query, TanStack Table, Tailwind, shadcn/ui, WebSocket/SSE for live logs.

---

## 7. Configuration

```env
DATABASE_URL=postgresql+psycopg://agent_bug_lab:agent_bug_lab@localhost:5432/agent_bug_lab
REDIS_URL=redis://localhost:6379/0

DATA_DIR=./data
FIXED_REPO_ROOT=/workspace/target

CODEX_CLI_BIN=codex
CLAUDE_CODE_CLI_BIN=claude
DEFAULT_HARNESS=codex
DEFAULT_MODEL=gpt-5.5-codex

RUN_TIMEOUT_SECONDS=7200
SEARCHER_MIN_FINDINGS=1
SEARCHER_MAX_FINDINGS=5
REVIEW_STALE_AFTER_DAYS=5
```

---

## 8. Database Schema

### `projects`
```sql
id TEXT PK, name TEXT NOT NULL, bug_bounty_url TEXT NOT NULL,
repo_path TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now()
```

### `bugs` — exact contract
```sql
id TEXT PK,
severity TEXT NOT NULL,
scope_id TEXT NOT NULL REFERENCES projects(id),
description TEXT NOT NULL,
repro_path TEXT NOT NULL,
repro_usage TEXT NOT NULL,
missing_for_full_chain TEXT NOT NULL
```
`scope_id` means project_id in this version. Kept as `scope_id` because the agent JSON contract uses it. Allowed severity: `critical, high, medium, low, info, unknown`. All findings stored (strong, weak, incomplete, duplicate, not-yet-filable); only invalid JSON is rejected.

### `agent_runs`
```sql
id TEXT PK, project_id TEXT REFERENCES projects(id), role TEXT,
harness TEXT, model TEXT, status TEXT, objective TEXT,
resume_from_run_id TEXT, harness_session_id TEXT, data_dir TEXT,
started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
raw_input JSONB NOT NULL, raw_output JSONB, error TEXT,
created_at TIMESTAMPTZ DEFAULT now()
```
Roles: `searcher_agent, cleaner_agent, critical_thinking_agent`. Statuses: `queued, running, succeeded, failed, cancelled`.

### `agent_logs`
```sql
id BIGSERIAL PK, run_id TEXT REFERENCES agent_runs(id),
level TEXT, message TEXT, payload JSONB, created_at TIMESTAMPTZ DEFAULT now()
```
Levels: `debug, info, warning, error`.

### `bug_reviews`
```sql
id TEXT PK, bug_id TEXT (no FK), project_id TEXT REFERENCES projects(id),
run_id TEXT REFERENCES agent_runs(id) NULL, reviewer_role TEXT,
decision TEXT, notes TEXT, created_at TIMESTAMPTZ DEFAULT now()
```
`bug_id` has no FK — cleaner-agent may delete bugs; reviews must survive. Reviewer roles: `cleaner_agent, critical_thinking_agent, human`. Decisions: `kept, removed, refined, needs_more_work`.

### `settings`
```sql
id TEXT PK, selected_harness TEXT, selected_model TEXT,
use_resume_when_available BOOLEAN DEFAULT true,
updated_at TIMESTAMPTZ DEFAULT now()
```
Singleton row: `id = 'global'`.

---

## 9. Review Queue Logic

A bug is in the review queue when it has never been reviewed OR its latest review is at least `REVIEW_STALE_AFTER_DAYS` old (default 5).

---

## 10. Data Directory Rules

- `data/project_<project_id>/`  → `project.json`, `created_searcher_run_id.txt`
- `data/searcher_<run_id>/`     → `input.json, output.json, stdout.log, stderr.log, validated_bugs.json, ingest_report.json, harness_command.json`
- `data/cleaner_<review_id>/`   → `input.json, output.json, stdout.log, stderr.log, selected_bugs_before.json, removed_bugs.json, kept_bugs.json, review_notes.json, harness_command.json`
- `data/critical_<run_id>/`     → `input.json, output.json, stdout.log, stderr.log, bug_before.json, bug_after.json, harness_command.json`

DB is canonical; `data/` is forensic history.

---

## 11. Bug Object Contract

```json
{
  "id": "bug_000001",
  "severity": "high",
  "scope_id": "project_000001",
  "description": "...",
  "repro_path": "repros/bug_000001.py",
  "repro_usage": "python repros/bug_000001.py",
  "missing_for_full_chain": "..."
}
```
`repro_path` may be `"not_created"`. `missing_for_full_chain` must not be empty.

---

## 12. Searcher Harness Contract

Input fields: `task_id, role=searcher_agent, scope_id, project{...}, objective, constraints{read_only, min_findings, max_findings, output_format, do_not_modify_repo}, required_bug_fields[]`.

Output: `task_id, status, bugs[1..5], notes[]`.

---

## 13. Cleaner Harness Contract

Input: `task_id, role=cleaner_agent, project{...}, selected_bugs[], objective, constraints`.
Output: `task_id, status, remove_bug_ids[], keep_bug_ids[], decisions[]`.

Backend: delete bugs in `remove_bug_ids`; write `bug_reviews` rows for removed AND kept; write artifact files.

---

## 14. Critical-Thinking Harness Contract

Input: `task_id, role=critical_thinking_agent, project{...}, bug{...}, objective, constraints`.
Output: `task_id, status, bug{...} (id and scope_id unchanged), review_note`.

Backend: update bug; insert bug_reviews row decision=refined; write before/after.

---

## 15. Harness Invocation

Registry:
```json
{
  "codex":       {"bin_env": "CODEX_CLI_BIN",       "model_arg": "--model", "resume_arg": "--resume", "supports_resume": true, "supports_raw_json": true},
  "claude_code": {"bin_env": "CLAUDE_CODE_CLI_BIN", "model_arg": "--model", "resume_arg": "--resume", "supports_resume": true, "supports_raw_json": true}
}
```
Rules:
- always pass `--model <selected_model>`
- use `--resume` only when `resume_from_run_id` or `harness_session_id` exists
- never `--resume` on a brand-new run
- persist final command to `harness_command.json`
- stream stdout/stderr into `agent_logs`
- store raw stdout/stderr in run data directory

Shape: `<bin> --model <selected_model> [--resume <harness_session_id>] < input.json`.

Harness-specific flags live in `harness_runner.py` only.

---

## 16. API Endpoints

### Projects
`GET /api/projects`, `POST /api/projects` (auto-enqueues searcher), `GET /api/projects/{id}`, `DELETE /api/projects/{id}`, `POST /api/projects/{id}/start-searcher`.

### Runs
`GET /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/cancel`, `POST /api/runs/{id}/resume`, `GET /api/runs/{id}/logs`, `GET /api/runs/{id}/stream`.

### Bugs
`GET /api/bugs`, `POST /api/bugs`, `GET /api/bugs/{id}`, `PATCH /api/bugs/{id}`, `DELETE /api/bugs/{id}`, `POST /api/bugs/export`.

### Review Queue
`GET /api/review-queue`, `POST /api/review-queue/clean` (body: `{project_id, bug_ids[]}`), `POST /api/review-queue/critical`.

### Settings
`GET /api/settings`, `PATCH /api/settings`, `GET /api/harnesses`.

---

## 17. Web UI Pages

`/projects`, `/projects/:id`, `/runs`, `/runs/:id`, `/bugs`, `/bugs/:id`, `/review-queue`, `/settings`. (See spec for full column/filter requirements.)

---

## 18. Observability

Structured events:
`project.created, project.data_dir.created, searcher.auto_queued, run.queued, run.started, run.data_dir.created, harness.command.created, harness.input.created, harness.process.spawned, harness.stdout.line, harness.stderr.line, harness.output.received, harness.output.validated, bugs.ingested, review_queue.calculated, cleaner.selected_bugs.loaded, cleaner.bugs.removed, critical.bug.refined, run.succeeded, run.failed.`

Each event payload includes `run_id, project_id, harness, model, role, data_dir`.

---

## 19. Background Job Behavior

- **Project creation** → row → `data/project_<id>` → `project.json` → enqueue searcher → return response with run id.
- **Searcher** → load run → `data/searcher_<run_id>` → input.json → harness_command.json → spawn CLI → stream stdout/stderr → output.json → validate → insert bugs → validated_bugs.json → mark succeeded/failed.
- **Cleaner** → run row → `data/cleaner_<review_id>` → selected_bugs_before.json → invoke harness → validate → delete remove_bug_ids → bug_reviews rows → removed_bugs.json/kept_bugs.json → succeeded/failed.
- **Critical** → run row → `data/critical_<run_id>` → bug_before.json → invoke harness → validate refined bug → update bug → bug_reviews row → bug_after.json → succeeded/failed.

---

## 20. Validation Rules

Searcher: valid JSON; status in {ok, failed}; bugs length 1..5; exact fields; scope_id matches; severity allowed; missing_for_full_chain non-empty.
Cleaner: valid JSON; remove/keep id arrays subset of selected_bugs; decisions explain each removed bug.
Critical: valid JSON; output.bug matches exact schema; id unchanged; scope_id unchanged.

Invalid JSON → run marked failed; stdout/stderr/raw output preserved; error surfaced.

---

## 21. Deletion Semantics

Cleaner removal = delete bug row, preserve `bug_reviews` rows, preserve artifacts/logs. Manual deletion = same, with `reviewer_role=human, decision=removed`.

---

## 22. MVP Acceptance Criteria

See spec §22. Highlights: create project → auto searcher; settings drive `--model`/`--resume`; bugs use exact 7-field schema; review queue surfaces stale/unreviewed; cleaner removes bad bugs; artifacts written per run; logs streamable.

---

## 23. Non-Goals for MVP

multi-user auth, billing, cloud deploy, distributed swarm, live exploitation, source modification, browser IDE, complex perms, automatic bounty submission.

---

## 24. Design Principle

Observable bug-finding workbench. Agents may be messy; the app stays clean. Every project starts with a searcher. Every valid candidate is stored. Every cleaner run leaves artifacts. Every removed bug leaves review history. Every harness command is inspectable.
