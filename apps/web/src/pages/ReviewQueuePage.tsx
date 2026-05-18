import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Brain, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SeverityBadge } from "@/components/SeverityBadge";
import { fmtDateTime, truncate } from "@/lib/format";

export function ReviewQueuePage() {
  const navigate = useNavigate();
  const { data: queue } = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => api.reviewQueue(),
    refetchInterval: 3000,
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const projectId = useMemo(() => {
    if (!queue || queue.length === 0) return null;
    const scopes = new Set(queue.map((b) => b.scope_id));
    return scopes.size === 1 ? queue[0].scope_id : null;
  }, [queue]);

  const toggle = (id: string) => {
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const clean = useMutation({
    mutationFn: () => api.runCleaner({ bug_ids: Array.from(selected) }),
    onSuccess: (run) => navigate(`/runs/${run.id}`),
  });

  const critical = useMutation({
    mutationFn: () => {
      if (selected.size !== 1) throw new Error("select exactly one bug");
      const id = Array.from(selected)[0];
      return api.runCritical({ bug_id: id });
    },
    onSuccess: (run) => navigate(`/runs/${run.id}`),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Review queue</h1>
        <p className="text-sm text-text-muted">
          Bugs with no review or whose last review is stale (default {">"} 5 days).
          Select a group and run the cleaner.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <span className="flex-1">
              {queue?.length ?? 0} bug(s) due · {selected.size} selected
              {projectId ? <span className="ml-2 text-text-subtle">({projectId})</span> : null}
            </span>
            <Button
              variant="primary"
              onClick={() => clean.mutate()}
              disabled={selected.size === 0 || clean.isPending}
              data-testid="run-cleaner-button"
            >
              <Sparkles className="h-4 w-4" /> Run cleaner
              {selected.size > 0 ? ` (${selected.size})` : ""}
            </Button>
            <Button
              onClick={() => critical.mutate()}
              disabled={selected.size !== 1 || critical.isPending}
              data-testid="run-critical-from-queue"
            >
              <Brain className="h-4 w-4" /> Critical-thinking
            </Button>
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {queue && queue.length > 0 ? (
            <table className="w-full text-left text-sm" data-testid="review-queue-table">
              <thead className="text-xs uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="w-8 px-4 py-2">
                    <input
                      type="checkbox"
                      data-testid="review-queue-select-all"
                      checked={selected.size > 0 && selected.size === queue.length}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? new Set(queue.map((b) => b.id))
                            : new Set(),
                        )
                      }
                    />
                  </th>
                  <th className="px-4 py-2">id</th>
                  <th className="px-4 py-2">severity</th>
                  <th className="px-4 py-2">description</th>
                  <th className="px-4 py-2">last review</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((b) => (
                  <tr key={b.id} className="border-t border-border hover:bg-bg-hover">
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        data-testid={`review-queue-row-${b.id}`}
                        checked={selected.has(b.id)}
                        onChange={() => toggle(b.id)}
                      />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link to={`/bugs/${b.id}`} className="text-accent hover:text-accent-hover">
                        {b.id}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <SeverityBadge severity={b.severity} />
                    </td>
                    <td className="px-4 py-2 text-text-muted">{truncate(b.description, 80)}</td>
                    <td className="px-4 py-2 text-text-muted">
                      {b.last_reviewed_at ? fmtDateTime(b.last_reviewed_at) : "never"}
                      {b.last_decision ? ` · ${b.last_decision}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4 text-sm text-text-subtle">Review queue is empty.</div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
