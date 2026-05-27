import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowRight, Loader2, ScanSearch, ServerCog, TerminalSquare } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { LogStream } from "@/components/LogStream";
import { useRunStream } from "@/hooks/useRunStream";
import { fmtDuration } from "@/lib/format";
import type { Status } from "@/lib/types";

const TERMINAL: Status[] = ["succeeded", "failed", "cancelled"];

interface Phase {
  // Keeping `static` as the first key is purely a stable internal label; the
  // visible label is set in `PHASES`. Backwards compat with existing
  // data-testid selectors.
  key: "static" | "agent" | "dossier";
  label: string;
  hint: string;
  starts: string[];   // any log message in this list flips the phase to "running"
  done: string[];     // any here flips it to "done"
}

const PHASES: Phase[] = [
  {
    key: "static",
    label: "Briefing the recon agent",
    hint: "spinning up the harness and handing over the bounty URL",
    starts: ["prepare.run.started"],
    done: ["prepare.phase.recon.start"],
  },
  {
    key: "agent",
    label: "Recon agent hunting",
    hint: "pulling repos / contracts / prior audits / known incidents from the bounty URL",
    starts: ["prepare.phase.recon.start"],
    done: ["prepare.phase.recon.done"],
  },
  {
    key: "dossier",
    label: "Validating + saving dossier",
    hint: "contract check → projects.prepare_dossier",
    starts: ["prepare.phase.recon.done", "harness.output.received"],
    done: ["prepare.dossier.saved"],
  },
];

type PhaseState = "pending" | "running" | "done" | "failed";

export function ProjectPreparePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();

  // Hydrate the project (so we know the prepare_run_id even on a hard refresh).
  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => api.getProject(id),
    enabled: !!id,
    refetchInterval: (q) =>
      // refetch every 2s until dossier is saved, then stop
      (q.state.data?.prepare_dossier ? false : 2000),
  });

  const runId = project?.prepare_run_id ?? undefined;
  const { run, logs, tick, endedAt } = useRunStream(runId);
  void tick; // tick subscription keeps the WS warm; nothing else to do

  const status = endedAt ?? run?.status;
  const isTerminal = status != null && TERMINAL.includes(status);
  const isSucceeded = status === "succeeded";

  const phaseStates = useMemo<Record<Phase["key"], PhaseState>>(() => {
    const result: Record<Phase["key"], PhaseState> = {
      static: "pending",
      agent: "pending",
      dossier: "pending",
    };
    const seen = new Set(logs.map((l) => l.message));
    for (const p of PHASES) {
      if (p.done.some((m) => seen.has(m))) result[p.key] = "done";
      else if (p.starts.some((m) => seen.has(m))) result[p.key] = "running";
    }
    if (status === "failed" || status === "cancelled") {
      // Mark the first non-done phase as failed for clarity
      for (const p of PHASES) {
        if (result[p.key] !== "done") {
          result[p.key] = "failed";
          break;
        }
      }
    }
    return result;
  }, [logs, status]);

  // Auto-navigate to the project page ~1.2s after success so the user sees
  // the green checks land before the redirect.
  useEffect(() => {
    if (!isSucceeded) return;
    const t = window.setTimeout(() => navigate(`/projects/${id}`), 1200);
    return () => window.clearTimeout(t);
  }, [isSucceeded, id, navigate]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-text-subtle">prepare</div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <ScanSearch className="h-6 w-6 text-accent" />
            Hunting the terrain…
          </h1>
          <div className="mt-1 text-sm text-text-muted">
            {project ? (
              <>
                Researching{" "}
                <a
                  href={project.bug_bounty_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono break-all hover:text-text"
                >
                  {project.bug_bounty_url}
                </a>{" "}
                — finding in-scope repos / contracts, pulling history, lore,
                prior audits, and known incidents.
              </>
            ) : (
              "Loading project…"
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => navigate(`/projects/${id}`)}
            disabled={!isTerminal}
            data-testid="prepare-view-project"
            title={
              isTerminal
                ? "Open the project page"
                : "Available once prepare finishes"
            }
          >
            View project <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <ServerCog className="h-4 w-4 text-text-muted" />
            Pipeline
          </span>
          <span className="text-xs font-normal text-text-subtle font-mono">
            {run ? (
              <>
                run <Link to={`/runs/${run.id}`} className="text-accent hover:text-accent-hover">{run.id}</Link>{" "}
                · {run.harness} · {run.model}
                {run.effort ? ` · ${run.effort}` : ""}
                {" · "}
                {fmtDuration(run.started_at, run.finished_at)}
              </>
            ) : (
              "spinning up…"
            )}
          </span>
        </CardHeader>
        <CardBody className="space-y-2">
          {PHASES.map((p) => (
            <PhaseRow key={p.key} phase={p} state={phaseStates[p.key]} />
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <TerminalSquare className="h-4 w-4 text-text-muted" />
            Hunting log
          </span>
          <span className="text-xs font-normal text-text-subtle">
            {logs.length} event{logs.length === 1 ? "" : "s"}
          </span>
        </CardHeader>
        <CardBody>
          <LogStream rows={logs} />
        </CardBody>
      </Card>

      {status === "failed" ? (
        <Card className="border-red-600/40">
          <CardBody className="text-sm text-red-400" data-testid="prepare-failed">
            Prepare failed. {run?.error ? <>Reason: <span className="font-mono text-xs">{run.error}</span></> : null}
            <div className="mt-2 text-xs text-text-muted">
              You can still open the project page and start a searcher manually,
              but it will run without a dossier.
            </div>
          </CardBody>
        </Card>
      ) : null}

      {isSucceeded ? (
        <Card className="border-green-600/40">
          <CardBody className="text-sm text-green-400" data-testid="prepare-succeeded">
            Dossier saved. Redirecting to the project page…
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

function PhaseRow({ phase, state }: { phase: Phase; state: PhaseState }) {
  return (
    <div
      className="flex items-center justify-between rounded-md border border-border bg-bg-subtle px-3 py-2"
      data-testid={`prepare-phase-${phase.key}`}
      data-state={state}
    >
      <div>
        <div className="text-sm text-text flex items-center gap-2">
          <PhaseIcon state={state} />
          {phase.label}
        </div>
        <div className="text-xs text-text-subtle">{phase.hint}</div>
      </div>
      <div className="font-mono text-[11px] uppercase tracking-wide text-text-subtle">
        {state}
      </div>
    </div>
  );
}

function PhaseIcon({ state }: { state: PhaseState }) {
  if (state === "running") {
    return <Loader2 className="h-4 w-4 animate-spin text-accent" />;
  }
  if (state === "done") {
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" />;
  }
  if (state === "failed") {
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />;
  }
  return <span className="inline-block h-2.5 w-2.5 rounded-full bg-text-subtle/40" />;
}
