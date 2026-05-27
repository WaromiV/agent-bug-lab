import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FileDown, Layers, Play, Trash2, X } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/StatusBadge";
import { SeverityBadge } from "@/components/SeverityBadge";
import { ScopeManager } from "@/components/ScopeManager";
import { AgentRunningOverlay } from "@/components/AgentRunningOverlay";
import { PrepareDossierCard } from "@/components/PrepareDossierCard";
import { StaticFactsCard } from "@/components/StaticFactsCard";
import { DebateButton } from "@/components/DebateButton";
import { fmtDateTime, fmtDuration, truncate } from "@/lib/format";

export function ProjectDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => api.getProject(id),
    enabled: !!id,
  });
  const { data: runs } = useQuery({
    queryKey: ["runs", { project_id: id }],
    queryFn: () => api.listRuns({ project_id: id }),
    refetchInterval: 2000,
  });
  const { data: bugs } = useQuery({
    queryKey: ["bugs", { project_id: id }],
    queryFn: () => api.listBugs({ project_id: id }),
    refetchInterval: 2500,
  });
  const [showSearcherModal, setShowSearcherModal] = useState(false);
  const [agentCount, setAgentCount] = useState(4);
  const start = useMutation({
    mutationFn: (count: number) => api.startSearcher(id, count),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      setShowSearcherModal(false);
      if (r.run_ids.length === 1) {
        navigate(`/runs/${r.run_ids[0]}`);
      }
    },
  });
  const del = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => navigate("/projects"),
  });

  const [exportError, setExportError] = useState<string | null>(null);
  const [dedupError, setDedupError] = useState<string | null>(null);
  const [dedupResult, setDedupResult] = useState<
    | { groups_count: number; deleted_count: number; candidates_seen: number }
    | null
  >(null);

  const errToString = (err: unknown): string =>
    err instanceof ApiError
      ? typeof err.detail === "string"
        ? err.detail
        : JSON.stringify(err.detail)
      : err instanceof Error
        ? err.message
        : String(err);

  const exporter = useMutation({
    mutationFn: () => api.exportProject(id),
    onMutate: () => setExportError(null),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1_000);
    },
    onError: (err) => setExportError(errToString(err)),
  });

  const dedup = useMutation({
    mutationFn: () => api.dedupProject(id),
    onMutate: () => {
      setDedupError(null);
      setDedupResult(null);
    },
    onSuccess: (r) => {
      setDedupResult({
        groups_count: r.groups_count,
        deleted_count: r.deleted_count,
        candidates_seen: r.candidates_seen,
      });
      qc.invalidateQueries({ queryKey: ["bugs"] });
      qc.invalidateQueries({ queryKey: ["project", id] });
    },
    onError: (err) => setDedupError(errToString(err)),
  });

  const bugCount = bugs?.length ?? 0;

  if (!project) return <div className="text-sm text-text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-text-subtle">project</div>
          <h1 className="font-mono text-2xl">{project.name}</h1>
          <div className="mt-1 text-text">{project.id}</div>
          <a
            href={project.bug_bounty_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-text-muted hover:text-text"
          >
            {project.bug_bounty_url}
          </a>
        </div>
        <div className="flex gap-2">
          <Button
            variant="primary"
            onClick={() => setShowSearcherModal(true)}
            disabled={start.isPending}
            data-testid="start-searcher-button"
          >
            <Play className="h-4 w-4" /> Start searcher
          </Button>
          <Button
            variant="outline"
            onClick={() => dedup.mutate()}
            disabled={dedup.isPending || exporter.isPending || bugCount < 2}
            data-testid="start-dedup-button"
            title={
              bugCount < 2
                ? "Need at least 2 bugs to dedup"
                : "Run the dedup agent — identifies duplicate groups and deletes the non-canonical copies (the canonical is kept)"
            }
          >
            <Layers className="h-4 w-4" /> Start dedup
          </Button>
          <Button
            variant="outline"
            onClick={() => exporter.mutate()}
            disabled={exporter.isPending || dedup.isPending || bugCount === 0}
            data-testid="export-findings-button"
            title={
              bugCount === 0
                ? "No bugs to export yet"
                : "Run the curation agent and download a single curated Markdown of the strongest confirmed findings"
            }
          >
            <FileDown className="h-4 w-4" /> Export findings
          </Button>
          <Button
            variant="danger"
            onClick={() => del.mutate()}
            disabled={del.isPending}
          >
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
        </div>
      </div>

      {exportError ? (
        <Card className="border-status-failed/40">
          <CardBody className="text-xs text-status-failed" data-testid="export-error">
            export failed: {exportError}
          </CardBody>
        </Card>
      ) : null}

      {dedupError ? (
        <Card className="border-status-failed/40">
          <CardBody className="text-xs text-status-failed" data-testid="dedup-error">
            dedup failed: {dedupError}
          </CardBody>
        </Card>
      ) : null}

      {dedupResult ? (
        <Card className="border-status-succeeded/40">
          <CardBody
            className="flex items-center justify-between text-xs text-status-succeeded"
            data-testid="dedup-success"
          >
            <span>
              dedup complete — {dedupResult.deleted_count} duplicate
              {dedupResult.deleted_count === 1 ? "" : "s"} deleted across{" "}
              {dedupResult.groups_count} group
              {dedupResult.groups_count === 1 ? "" : "s"} (of{" "}
              {dedupResult.candidates_seen} candidates seen).
            </span>
            <button
              type="button"
              className="text-text-subtle hover:text-text"
              onClick={() => setDedupResult(null)}
            >
              dismiss
            </button>
          </CardBody>
        </Card>
      ) : null}

      {exporter.isPending ? (
        <AgentRunningOverlay
          title="Curating findings…"
          description={
            <>
              Running the export agent (Opus · max) over {bugCount} candidate
              {bugCount === 1 ? "" : "s"}. Confirmed high-impact findings only;
              duplicates and low-confidence items are dropped. Your download
              starts automatically when the agent finishes.
            </>
          }
          expectedHint="typical 1–5 min"
          testId="export-loading-overlay"
        />
      ) : null}

      {dedup.isPending ? (
        <AgentRunningOverlay
          title="Finding duplicates…"
          description={
            <>
              Running the dedup agent (Opus · max) across {bugCount} bug
              {bugCount === 1 ? "" : "s"}. It identifies duplicate groups,
              keeps the strongest writeup per group, and deletes the others.
              The server validates every id before any delete.
            </>
          }
          expectedHint="typical 1–5 min"
          testId="dedup-loading-overlay"
        />
      ) : null}


      <PrepareDossierCard project={project} />

      <StaticFactsCard project={project} />

      <ScopeManager projectId={project.id} />

      <Card>
        <CardHeader>Recent runs</CardHeader>
        <CardBody className="p-0">
          {runs && runs.length > 0 ? (
            <table className="w-full text-left text-sm" data-testid="project-runs-table">
              <thead className="text-xs uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="px-4 py-2">id</th>
                  <th className="px-4 py-2">role</th>
                  <th className="px-4 py-2">status</th>
                  <th className="px-4 py-2">harness · model</th>
                  <th className="px-4 py-2">duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-t border-border hover:bg-bg-hover">
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/runs/${r.id}`} className="text-accent hover:text-accent-hover">
                        {r.id}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-text-muted">{r.role}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-4 py-2 text-text-muted">
                      {r.harness} · {r.model}
                    </td>
                    <td className="px-4 py-2 text-text-muted">
                      {fmtDuration(r.started_at, r.finished_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4 text-sm text-text-subtle">No runs yet.</div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Bugs in this project</CardHeader>
        <CardBody className="p-0">
          {bugs && bugs.length > 0 ? (
            <table className="w-full text-left text-sm" data-testid="project-bugs-table">
              <thead className="text-xs uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="px-4 py-2">id</th>
                  <th className="px-4 py-2">severity</th>
                  <th className="px-4 py-2">description</th>
                  <th className="px-4 py-2">debate</th>
                </tr>
              </thead>
              <tbody>
                {bugs.map((b) => (
                  <tr key={b.id} className="border-t border-border hover:bg-bg-hover">
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/bugs/${b.id}`} className="text-accent hover:text-accent-hover">
                        {b.id}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <SeverityBadge severity={b.severity} />
                    </td>
                    <td className="px-4 py-2 text-text-muted">{truncate(b.description, 100)}</td>
                    <td className="px-4 py-2">
                      <DebateButton bugId={b.id} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4 text-sm text-text-subtle">No bugs ingested yet.</div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Metadata</CardHeader>
        <CardBody className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <div className="text-xs text-text-subtle">repo_path</div>
            <div className="font-mono">{project.repo_path}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">created</div>
            <div>{fmtDateTime(project.created_at)}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">total bugs</div>
            <div data-testid="project-bug-count">{bugs?.length ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-text-subtle">total runs</div>
            <div>{runs?.length ?? "—"}</div>
          </div>
        </CardBody>
      </Card>

      {showSearcherModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-lg border border-border bg-bg-base p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Start searcher agents</h3>
              <button
                onClick={() => setShowSearcherModal(false)}
                className="text-text-muted hover:text-text"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="mb-4 text-sm text-text-muted">
              How many parallel agents should search this project?
            </p>
            <div className="mb-4 flex items-center gap-3">
              {[1, 2, 4, 8, 10, 15].map((n) => (
                <button
                  key={n}
                  onClick={() => setAgentCount(n)}
                  className={`rounded-md px-3 py-1.5 text-sm font-mono transition-colors ${
                    agentCount === n
                      ? "bg-accent text-white"
                      : "border border-border bg-bg-subtle text-text-muted hover:bg-bg-hover"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <input
              type="range"
              min={1}
              max={20}
              value={agentCount}
              onChange={(e) => setAgentCount(Number(e.target.value))}
              className="mb-2 w-full accent-accent"
            />
            <div className="mb-4 text-center text-xs text-text-subtle">
              {agentCount} agent{agentCount > 1 ? "s" : ""} · opus · max effort
            </div>
            <div className="flex gap-2">
              <Button
                variant="primary"
                onClick={() => start.mutate(agentCount)}
                disabled={start.isPending}
                className="flex-1"
              >
                {start.isPending
                  ? `Launching ${agentCount}...`
                  : `Launch ${agentCount} agent${agentCount > 1 ? "s" : ""}`}
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowSearcherModal(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
