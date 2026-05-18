import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SeverityBadge } from "@/components/SeverityBadge";
import { fmtDateTime, truncate } from "@/lib/format";

const sevOptions = [
  { label: "any severity", value: "" },
  { label: "critical", value: "critical" },
  { label: "high", value: "high" },
  { label: "medium", value: "medium" },
  { label: "low", value: "low" },
  { label: "info", value: "info" },
  { label: "unknown", value: "unknown" },
];

export function BugsPage() {
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const { data: bugs } = useQuery({
    queryKey: ["bugs", { search, severity }],
    queryFn: () =>
      api.listBugs({
        search: search || undefined,
        severity: severity || undefined,
      }),
    refetchInterval: 3000,
  });
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Bugs</h1>
        <p className="text-sm text-text-muted">
          Every candidate the searcher has produced — strong, weak, or
          incomplete.
        </p>
      </div>
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <span className="flex-1">{bugs?.length ?? 0} bug(s)</span>
            <Input
              placeholder="search description…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="bug-search"
              className="w-56"
            />
            <Select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              options={sevOptions}
              data-testid="bug-severity-filter"
              className="w-40"
            />
          </div>
        </CardHeader>
        <CardBody className="p-0">
          <table className="w-full text-left text-sm" data-testid="bugs-table">
            <thead className="text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-4 py-2">id</th>
                <th className="px-4 py-2">severity</th>
                <th className="px-4 py-2">project · scope</th>
                <th className="px-4 py-2">description</th>
                <th className="px-4 py-2">repro</th>
                <th className="px-4 py-2">last review</th>
              </tr>
            </thead>
            <tbody>
              {bugs?.map((b) => (
                <tr key={b.id} className="border-t border-border hover:bg-bg-hover">
                  <td className="px-4 py-2 font-mono text-xs">
                    <Link to={`/bugs/${b.id}`} className="text-accent hover:text-accent-hover">
                      {b.id}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <SeverityBadge severity={b.severity} />
                  </td>
                  <td className="px-4 py-2 text-xs">
                    <div className="font-mono text-text-muted">{b.project_id ?? "?"}</div>
                    <div className="text-text">{b.scope_name ?? b.scope_id}</div>
                  </td>
                  <td className="px-4 py-2 text-text-muted">{truncate(b.description, 70)}</td>
                  <td className="px-4 py-2 font-mono text-xs text-text-muted">
                    {b.repro_path}
                  </td>
                  <td className="px-4 py-2 text-text-muted">
                    {b.last_reviewed_at ? fmtDateTime(b.last_reviewed_at) : "never"}
                    {b.last_decision ? ` · ${b.last_decision}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </div>
  );
}
