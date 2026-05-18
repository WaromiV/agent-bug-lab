import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { fmtDateTime, fmtDuration, truncate } from "@/lib/format";

export function RunsPage() {
  const { data: runs } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.listRuns(),
    refetchInterval: 2000,
  });
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Runs</h1>
        <p className="text-sm text-text-muted">
          Every searcher, cleaner, and critical-thinking run.
        </p>
      </div>
      <Card>
        <CardHeader>{runs?.length ?? 0} run(s)</CardHeader>
        <CardBody className="p-0">
          <table className="w-full text-left text-sm" data-testid="runs-table">
            <thead className="text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-4 py-2">id</th>
                <th className="px-4 py-2">role</th>
                <th className="px-4 py-2">status</th>
                <th className="px-4 py-2">harness · model</th>
                <th className="px-4 py-2">project</th>
                <th className="px-4 py-2">started</th>
                <th className="px-4 py-2">duration</th>
                <th className="px-4 py-2">error</th>
              </tr>
            </thead>
            <tbody>
              {runs?.map((r) => (
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
                  <td className="px-4 py-2 font-mono text-xs">
                    <Link
                      to={`/projects/${r.project_id}`}
                      className="text-text-muted hover:text-text"
                    >
                      {r.project_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-text-muted">{fmtDateTime(r.started_at)}</td>
                  <td className="px-4 py-2 text-text-muted">
                    {fmtDuration(r.started_at, r.finished_at)}
                  </td>
                  <td className="px-4 py-2 text-status-failed">{truncate(r.error, 60)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </div>
  );
}
