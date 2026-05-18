import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PlayCircle, Wifi, WifiOff, XCircle } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useRunStream } from "@/hooks/useRunStream";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/StatusBadge";
import { LogStream } from "@/components/LogStream";
import { fmtDateTime, fmtDuration } from "@/lib/format";

export function RunDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { run, logs, connected, error: wsError } = useRunStream(id);

  const cancel = useMutation({
    mutationFn: () => api.cancelRun(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run", id] }),
  });
  const resume = useMutation({
    mutationFn: () => api.resumeRun(id),
    onSuccess: (r) => navigate(`/runs/${r.id}`),
  });

  if (!run) return <div className="text-sm text-text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-text-subtle">{run.role}</div>
          <h1 className="font-mono text-2xl">{run.id}</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-text-muted">
            <StatusBadge status={run.status} />
            <span>{run.harness} · {run.model}</span>
            <Link to={`/projects/${run.project_id}`} className="hover:text-text">
              {run.project_id}
            </Link>
            <span
              data-testid="ws-state"
              className={clsx(
                "inline-flex items-center gap-1 text-xs",
                connected ? "text-status-succeeded" : "text-text-subtle",
              )}
              title={connected ? "WebSocket connected" : "WebSocket disconnected"}
            >
              {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {connected ? "live" : "offline"}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {run.status === "running" || run.status === "queued" ? (
            <Button
              variant="danger"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
            >
              <XCircle className="h-4 w-4" /> Cancel
            </Button>
          ) : null}
          {run.role === "searcher_agent" &&
          (run.status === "succeeded" || run.status === "failed") ? (
            <Button
              variant="primary"
              onClick={() => resume.mutate()}
              disabled={resume.isPending}
            >
              <PlayCircle className="h-4 w-4" /> Resume
            </Button>
          ) : null}
        </div>
      </div>

      {wsError ? (
        <Card className="border-status-failed/40">
          <CardBody className="text-xs text-status-failed">
            websocket error: {wsError}
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>Metadata</CardHeader>
        <CardBody className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <div className="text-xs text-text-subtle">data_dir</div>
            <div className="font-mono">{run.data_dir}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">duration</div>
            <div data-testid="run-duration">
              {fmtDuration(run.started_at, run.finished_at)}
            </div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">started</div>
            <div>{fmtDateTime(run.started_at)}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">finished</div>
            <div>{fmtDateTime(run.finished_at)}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">resume_from</div>
            <div className="font-mono">{run.resume_from_run_id || "—"}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">harness_session_id</div>
            <div className="font-mono break-all">{run.harness_session_id || "—"}</div>
          </div>
        </CardBody>
      </Card>

      {run.error ? (
        <Card className="border-status-failed/40">
          <CardHeader className="text-status-failed">Failure</CardHeader>
          <CardBody>
            <pre className="overflow-auto whitespace-pre-wrap text-xs text-status-failed">
              {run.error}
            </pre>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <span>Live logs</span>
            <span data-testid="log-count" className="text-xs font-normal text-text-subtle">
              {logs.length} row{logs.length === 1 ? "" : "s"}
            </span>
          </div>
        </CardHeader>
        <CardBody>
          <LogStream rows={logs} />
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>raw input JSON</CardHeader>
          <CardBody>
            <pre
              data-testid="raw-input"
              className="scrollbar-thin max-h-72 overflow-auto rounded bg-bg-subtle p-3 font-mono text-xs"
            >
              {JSON.stringify(run.raw_input, null, 2)}
            </pre>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>raw output JSON</CardHeader>
          <CardBody>
            <pre
              data-testid="raw-output"
              className="scrollbar-thin max-h-72 overflow-auto rounded bg-bg-subtle p-3 font-mono text-xs"
            >
              {run.raw_output ? JSON.stringify(run.raw_output, null, 2) : "—"}
            </pre>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
