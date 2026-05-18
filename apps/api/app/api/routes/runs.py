from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.api.deps import ArqPool, DbSession
from app.core.ids import next_id
from app.core.logging import get_logger
from app.db.models import AgentRun
from app.db.session import SessionLocal
from app.schemas.run import LogRead, RunRead
from app.services import run_manager

log = get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

# Terminal run statuses — once we observe one we send a final frame and close.
_TERMINAL = {"succeeded", "failed", "cancelled"}


@router.get("", response_model=list[RunRead])
def list_runs(
    db: DbSession, project_id: str | None = Query(default=None), limit: int = Query(default=200, le=1000)
) -> list[RunRead]:
    runs = run_manager.list_runs(db, project_id=project_id, limit=limit)
    return [RunRead.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: str, db: DbSession) -> RunRead:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return RunRead.model_validate(run)


@router.post("/{run_id}/cancel", response_model=RunRead)
def cancel_run(run_id: str, db: DbSession) -> RunRead:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status in _TERMINAL:
        return RunRead.model_validate(run)
    run_manager.mark_cancelled(db, run)
    return RunRead.model_validate(run)


@router.post("/{run_id}/resume", response_model=RunRead)
async def resume_run(run_id: str, db: DbSession, pool: ArqPool) -> RunRead:
    original = db.get(AgentRun, run_id)
    if original is None:
        raise HTTPException(404, "run not found")
    if original.role != "searcher_agent":
        raise HTTPException(400, "only searcher runs can be resumed in MVP")

    new_run_id = next_id(db, "run")
    raw_input = dict(original.raw_input)
    raw_input["task_id"] = new_run_id
    new_run = run_manager.create_run(
        db,
        project_id=original.project_id,
        role=original.role,
        harness=original.harness,
        model=original.model,
        objective=original.objective,
        raw_input=raw_input,
        resume_from_run_id=original.id,
        harness_session_id=original.harness_session_id,
        run_id=new_run_id,
    )
    db.commit()
    await pool.enqueue_job("run_searcher", new_run.id)
    return RunRead.model_validate(new_run)


@router.get("/{run_id}/logs", response_model=list[LogRead])
def list_logs(
    run_id: str,
    db: DbSession,
    after_id: int | None = Query(default=None),
    limit: int = Query(default=500, le=2000),
) -> list[LogRead]:
    logs = run_manager.list_logs(db, run_id, after_id=after_id, limit=limit)
    return [LogRead.model_validate(log) for log in logs]


def _serialize_run(run: AgentRun) -> dict:
    return RunRead.model_validate(run).model_dump(mode="json")


def _serialize_log(row) -> dict:
    return LogRead.model_validate(row).model_dump(mode="json")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@router.websocket("/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    """
    Live stream of a single run.

    Message kinds the client may receive:
      - {kind: "run",  run: RunRead}      — full run state (on connect + on change)
      - {kind: "log",  row: LogRead}      — one new log row
      - {kind: "tick", now: ISO}          — server heartbeat (every poll cycle)
      - {kind: "end",  status: Status}    — terminal frame, server closes after
      - {kind: "error", error: str}       — fatal error before/after stream begins

    Server polls Postgres on a fixed cadence. Cheap and stateless; switch to
    Redis pub/sub if log volume per run grows.
    """
    await websocket.accept()
    last_log_id: int | None = None
    last_run_snapshot: dict | None = None
    try:
        while True:
            with SessionLocal() as s:
                run = s.get(AgentRun, run_id)
                if run is None:
                    await websocket.send_json({"kind": "error", "error": "run not found"})
                    return

                current = _serialize_run(run)
                if current != last_run_snapshot:
                    await websocket.send_json({"kind": "run", "run": current})
                    last_run_snapshot = current

                logs = run_manager.list_logs(s, run_id, after_id=last_log_id, limit=500)
                for row in logs:
                    await websocket.send_json({"kind": "log", "row": _serialize_log(row)})
                    last_log_id = row.id

                status = run.status

            await websocket.send_json({"kind": "tick", "now": _now_iso()})

            if status in _TERMINAL:
                await websocket.send_json({"kind": "end", "status": status})
                return

            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        log.exception("runs.ws.error", run_id=run_id, error=str(e))
        with contextlib.suppress(Exception):
            await websocket.send_json({"kind": "error", "error": str(e)})
