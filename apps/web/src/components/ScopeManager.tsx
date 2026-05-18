import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus, X } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import type { Scope } from "@/lib/types";

interface Props {
  projectId: string;
}

export function ScopeManager({ projectId }: Props) {
  const qc = useQueryClient();
  const { data: scopes } = useQuery({
    queryKey: ["scopes", projectId],
    queryFn: () => api.listScopes(projectId),
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.createScope(projectId, { name, description: description || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scopes", projectId] });
      setName("");
      setDescription("");
      setErr(null);
    },
    onError: (e: any) => setErr(e?.message ?? "create failed"),
  });

  return (
    <Card>
      <CardHeader>Scopes</CardHeader>
      <CardBody className="space-y-4">
        <p className="text-xs text-text-subtle">
          Scopes are research-direction groupings of issues (memory safety, IPC
          boundary, race conditions, …). Agents tag every finding with a scope
          and may freely create or rename scopes — but scopes are never
          deleted, so they accumulate as audit-trail vocabulary.
        </p>
        <table className="w-full text-left text-sm" data-testid="scopes-table">
          <thead className="text-xs uppercase tracking-wide text-text-muted">
            <tr>
              <th className="py-2 w-56">id</th>
              <th className="py-2">name</th>
              <th className="py-2">description</th>
              <th className="py-2 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {scopes?.map((s) => (
              <ScopeRow
                key={s.id}
                scope={s}
                editing={editingId === s.id}
                onEdit={() => setEditingId(s.id)}
                onClose={() => setEditingId(null)}
                onSaved={() => {
                  qc.invalidateQueries({ queryKey: ["scopes", projectId] });
                  setEditingId(null);
                }}
              />
            ))}
            {scopes && scopes.length === 0 ? (
              <tr><td colSpan={4} className="py-2 text-text-subtle">No scopes yet.</td></tr>
            ) : null}
          </tbody>
        </table>

        <div className="border-t border-border pt-3">
          <Label>Add a scope</Label>
          <div className="flex gap-2">
            <Input
              placeholder="name (e.g. Parser input validation)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="scope-new-name"
            />
            <Input
              placeholder="description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="scope-new-description"
            />
            <Button
              variant="primary"
              onClick={() => create.mutate()}
              disabled={!name || create.isPending}
              data-testid="scope-new-submit"
            >
              <Plus className="h-4 w-4" /> Add
            </Button>
          </div>
          {err ? <div className="mt-1 text-xs text-status-failed">{err}</div> : null}
        </div>
      </CardBody>
    </Card>
  );
}

function isPreliminary(scope: Scope): boolean {
  return scope.is_preliminary;
}

function ScopeRow({
  scope,
  editing,
  onEdit,
  onClose,
  onSaved,
}: {
  scope: Scope;
  editing: boolean;
  onEdit: () => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(scope.name);
  const [description, setDescription] = useState(scope.description ?? "");
  useEffect(() => {
    setName(scope.name);
    setDescription(scope.description ?? "");
  }, [scope, editing]);

  const save = useMutation({
    mutationFn: () =>
      api.patchScope(scope.id, { name, description: description || null }),
    onSuccess: onSaved,
  });

  const prelim = isPreliminary(scope);

  if (editing) {
    return (
      <tr className="border-t border-border bg-bg-hover">
        <td className="py-2 font-mono text-xs text-text-muted">{scope.id}</td>
        <td className="py-2 pr-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid={`scope-edit-name-${scope.id}`}
          />
        </td>
        <td className="py-2 pr-2">
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            data-testid={`scope-edit-description-${scope.id}`}
          />
        </td>
        <td className="py-2 text-right">
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending || !name}
            data-testid={`scope-edit-save-${scope.id}`}
            className="mr-2 text-status-succeeded hover:text-text"
          >
            <Check className="h-4 w-4" />
          </button>
          <button onClick={onClose} className="text-text-subtle hover:text-text">
            <X className="h-4 w-4" />
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-t border-border">
      <td className="py-2 font-mono text-xs text-text-muted">
        {scope.id}
        {prelim ? (
          <Badge className="ml-2 bg-bg-subtle text-text-muted">preliminary</Badge>
        ) : null}
      </td>
      <td className="py-2 text-text">{scope.name}</td>
      <td className="py-2 text-text-muted">{scope.description || "—"}</td>
      <td className="py-2 text-right">
        <button
          onClick={onEdit}
          className="text-text-subtle hover:text-text"
          title="rename"
          data-testid={`scope-edit-${scope.id}`}
        >
          <Pencil className="h-4 w-4" />
        </button>
      </td>
    </tr>
  );
}
