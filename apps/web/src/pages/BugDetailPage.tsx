import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SeverityBadge } from "@/components/SeverityBadge";
import { DebateButton } from "@/components/DebateButton";
import { DebateTranscriptCard } from "@/components/DebateTranscriptCard";
import type { Severity } from "@/lib/types";

const sevOptions = [
  { label: "critical", value: "critical" },
  { label: "high", value: "high" },
  { label: "medium", value: "medium" },
  { label: "low", value: "low" },
  { label: "info", value: "info" },
  { label: "unknown", value: "unknown" },
];

export function BugDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: bug } = useQuery({
    queryKey: ["bug", id],
    queryFn: () => api.getBug(id),
    enabled: !!id,
  });

  const projectId = bug?.project_id ?? null;
  const { data: scopes } = useQuery({
    queryKey: ["scopes", projectId],
    queryFn: () => api.listScopes(projectId!),
    enabled: !!projectId,
  });

  const [severity, setSeverity] = useState<Severity>("unknown");
  const [scopeId, setScopeId] = useState("");
  const [description, setDescription] = useState("");
  const [reproPath, setReproPath] = useState("");
  const [reproUsage, setReproUsage] = useState("");
  const [missing, setMissing] = useState("");
  const [savedNote, setSavedNote] = useState<string | null>(null);

  useEffect(() => {
    if (bug) {
      setSeverity(bug.severity);
      setScopeId(bug.scope_id);
      setDescription(bug.description);
      setReproPath(bug.repro_path);
      setReproUsage(bug.repro_usage);
      setMissing(bug.missing_for_full_chain);
    }
  }, [bug]);

  const save = useMutation({
    mutationFn: () =>
      api.patchBug(id, {
        severity,
        scope_id: scopeId,
        description,
        repro_path: reproPath,
        repro_usage: reproUsage,
        missing_for_full_chain: missing,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bug", id] });
      qc.invalidateQueries({ queryKey: ["bugs"] });
      setSavedNote("saved");
      setTimeout(() => setSavedNote(null), 1500);
    },
  });
  const del = useMutation({
    mutationFn: () => api.deleteBug(id),
    onSuccess: () => navigate("/bugs"),
  });

  if (!bug) return <div className="text-sm text-text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-text-subtle">bug</div>
          <h1 className="font-mono text-2xl">{bug.id}</h1>
          <div className="mt-1 flex items-center gap-2 text-sm">
            <SeverityBadge severity={bug.severity} />
            {bug.project_id ? (
              <Link
                to={`/projects/${bug.project_id}`}
                className="font-mono text-xs text-text-muted hover:text-text"
              >
                {bug.project_id}
              </Link>
            ) : null}
            <span className="text-xs text-text">
              {bug.scope_name ?? bug.scope_id}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <DebateButton bugId={id} size="md" />
          <Button variant="danger" onClick={() => del.mutate()} disabled={del.isPending}>
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>Edit</CardHeader>
        <CardBody className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Severity</Label>
              <Select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
                options={sevOptions}
              />
            </div>
            <div>
              <Label>Scope</Label>
              <Select
                data-testid="bug-scope-select"
                value={scopeId}
                onChange={(e) => setScopeId(e.target.value)}
                options={
                  scopes
                    ? scopes.map((s) => ({ label: `${s.name} (${s.id})`, value: s.id }))
                    : [{ label: bug.scope_id, value: bug.scope_id }]
                }
              />
            </div>
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="bug-desc"
            />
          </div>
          <div>
            <Label>repro_path</Label>
            <Input value={reproPath} onChange={(e) => setReproPath(e.target.value)} />
          </div>
          <div>
            <Label>repro_usage</Label>
            <Textarea
              rows={2}
              value={reproUsage}
              onChange={(e) => setReproUsage(e.target.value)}
            />
          </div>
          <div>
            <Label>missing_for_full_chain</Label>
            <Textarea
              rows={2}
              value={missing}
              onChange={(e) => setMissing(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              onClick={() => save.mutate()}
              disabled={save.isPending}
              data-testid="bug-save"
            >
              Save
            </Button>
            {savedNote ? (
              <span className="text-xs text-status-succeeded">{savedNote}</span>
            ) : null}
          </div>
        </CardBody>
      </Card>

      <DebateTranscriptCard bugId={id} />
    </div>
  );
}
