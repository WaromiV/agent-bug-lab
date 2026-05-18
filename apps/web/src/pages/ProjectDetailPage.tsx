import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Play, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/StatusBadge";
import { SeverityBadge } from "@/components/SeverityBadge";
import { ScopeManager } from "@/components/ScopeManager";
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
  const start = useMutation({
    mutationFn: () => api.startSearcher(id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${r.run_id}`);
    },
  });
  const del = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => navigate("/projects"),
  });

  if (!project) return <div className="text-sm text-text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-text-subtle">project</div>
          <h1 className="font-mono text-2xl">{project.id}</h1>
          <div className="mt-1 text-text">{project.name}</div>
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
            onClick={() => start.mutate()}
            disabled={start.isPending}
            data-testid="start-searcher-button"
          >
            <Play className="h-4 w-4" /> Start searcher
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
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4 text-sm text-text-subtle">No bugs ingested yet.</div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
