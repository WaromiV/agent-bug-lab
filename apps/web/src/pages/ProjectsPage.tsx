import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { fmtDateTime } from "@/lib/format";

export function ProjectsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
  });

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.createProject({ name, bug_bounty_url: url }),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      setOpen(false);
      setName("");
      setUrl("");
      setError(null);
      // Land on the prepare loading page so the user watches the static-facts
      // + threat-model-dossier hunt happen live before the project detail
      // page is revealed.
      navigate(`/projects/${resp.project.id}/prepare`);
    },
    onError: (e: any) => setError(e?.message ?? "create failed"),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="text-sm text-text-muted">
            Each project is one analysis target. Creating one auto-starts a searcher run.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setOpen(true)}
          data-testid="new-project-button"
        >
          <Plus className="h-4 w-4" /> New project
        </Button>
      </div>

      <Card>
        <CardHeader>{projects?.length ?? 0} project(s)</CardHeader>
        <CardBody className="p-0">
          {projects && projects.length > 0 ? (
            <table className="w-full text-left text-sm" data-testid="projects-table">
              <thead className="text-xs uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="px-4 py-2">id</th>
                  <th className="px-4 py-2">name</th>
                  <th className="px-4 py-2">bounty URL</th>
                  <th className="px-4 py-2">repo path</th>
                  <th className="px-4 py-2">created</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr
                    key={p.id}
                    className="border-t border-border hover:bg-bg-hover"
                  >
                    <td className="px-4 py-2 font-mono text-xs">
                      <Link
                        to={`/projects/${p.id}`}
                        className="text-accent hover:text-accent-hover"
                      >
                        {p.id}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{p.name}</td>
                    <td className="px-4 py-2">
                      <a
                        href={p.bug_bounty_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-text-muted hover:text-text"
                      >
                        {p.bug_bounty_url}
                      </a>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-text-muted">
                      {p.repo_path}
                    </td>
                    <td className="px-4 py-2 text-text-muted">
                      {fmtDateTime(p.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-6 text-sm text-text-subtle">
              No projects yet. Create one to kick off a searcher run.
            </div>
          )}
        </CardBody>
      </Card>

      <Dialog open={open} onClose={() => setOpen(false)} title="New project">
        <div className="space-y-3">
          <div>
            <Label htmlFor="proj-name">Name</Label>
            <Input
              id="proj-name"
              data-testid="new-project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="target-name"
            />
          </div>
          <div>
            <Label htmlFor="proj-url">Bug bounty / audit scope URL</Label>
            <Input
              id="proj-url"
              data-testid="new-project-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/bug-bounty"
            />
          </div>
          {error ? <div className="text-xs text-status-failed">{error}</div> : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              onClick={() => create.mutate()}
              disabled={!name || !url || create.isPending}
              data-testid="new-project-submit"
            >
              {create.isPending ? "creating…" : "Create + start prepare"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
