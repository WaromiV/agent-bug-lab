import { useEffect, useRef, useState } from "react";
import { api, subscribeRun, type RunEvent } from "@/lib/api";
import type { AgentLogRow, Run, Status } from "@/lib/types";

const TERMINAL: Status[] = ["succeeded", "failed", "cancelled"];

export interface RunStream {
  run: Run | null;
  logs: AgentLogRow[];
  /** Bumped by a 1s local interval while the run is active — drives live timers. */
  tick: number;
  /** Server-pushed terminal status, when received. */
  endedAt: Status | null;
  /** Connection state for UI affordances. */
  connected: boolean;
  error: string | null;
}

/**
 * Owns a single WebSocket per run. Combines:
 *   - server-pushed run state changes
 *   - server-pushed log rows
 *   - server-pushed ticks (~1s heartbeats)
 *   - a *local* 1s tick (while not terminal) so live timers keep ticking
 *     even when the server has nothing new to say
 */
export function useRunStream(runId: string | undefined): RunStream {
  const [run, setRun] = useState<Run | null>(null);
  const [logs, setLogs] = useState<AgentLogRow[]>([]);
  const [tick, setTick] = useState(0);
  const [endedAt, setEndedAt] = useState<Status | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seenLogIds = useRef<Set<number>>(new Set());

  // Hydrate via REST for fast first paint, then upgrade to WS.
  useEffect(() => {
    if (!runId) return;
    setRun(null);
    setLogs([]);
    setEndedAt(null);
    setError(null);
    seenLogIds.current = new Set();

    let cancelled = false;
    Promise.all([api.getRun(runId), api.listRunLogs(runId, undefined, 1000)])
      .then(([r, rows]) => {
        if (cancelled) return;
        setRun(r);
        rows.forEach((row) => seenLogIds.current.add(row.id));
        setLogs(rows);
      })
      .catch(() => {
        /* WS subscription below will surface live data */
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    setConnected(false);

    const handle = (e: RunEvent) => {
      setConnected(true);
      if (e.kind === "run") {
        setRun(e.run);
      } else if (e.kind === "log") {
        if (seenLogIds.current.has(e.row.id)) return;
        seenLogIds.current.add(e.row.id);
        setLogs((rows) => [...rows, e.row]);
      } else if (e.kind === "tick") {
        setTick((t) => t + 1);
      } else if (e.kind === "end") {
        setEndedAt(e.status);
      } else if (e.kind === "error") {
        setError(e.error);
      }
    };

    const close = subscribeRun(runId, handle);
    return () => {
      setConnected(false);
      close();
    };
  }, [runId]);

  // Local heartbeat so the running-timer ticks even between server pushes.
  useEffect(() => {
    if (!run) return;
    if (TERMINAL.includes(run.status)) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [run?.status, run]);

  return { run, logs, tick, endedAt, connected, error };
}
