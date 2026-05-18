import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

export function SettingsPage() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const { data: harnesses } = useQuery({
    queryKey: ["harnesses"],
    queryFn: api.listHarnesses,
  });

  const [selectedHarness, setSelectedHarness] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [useResume, setUseResume] = useState(true);
  const [savedNote, setSavedNote] = useState<string | null>(null);

  useEffect(() => {
    if (settings) {
      setSelectedHarness(settings.selected_harness);
      setSelectedModel(settings.selected_model);
      setUseResume(settings.use_resume_when_available);
    }
  }, [settings]);

  const save = useMutation({
    mutationFn: () =>
      api.patchSettings({
        selected_harness: selectedHarness,
        selected_model: selectedModel,
        use_resume_when_available: useResume,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setSavedNote("saved");
      setTimeout(() => setSavedNote(null), 2000);
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-text-muted">
          Harness and model used for every new agent run.
        </p>
      </div>
      <Card>
        <CardHeader>Harness execution</CardHeader>
        <CardBody className="space-y-4">
          <div>
            <Label htmlFor="harness">Harness</Label>
            <Select
              id="harness"
              data-testid="harness-select"
              value={selectedHarness}
              onChange={(e) => setSelectedHarness(e.target.value)}
              options={
                harnesses
                  ? harnesses.map((h) => ({ label: h.name, value: h.name }))
                  : []
              }
            />
            <p className="mt-1 text-xs text-text-subtle">
              Available harnesses are loaded from{" "}
              <code className="text-text-muted">/api/harnesses</code>.
            </p>
          </div>
          <div>
            <Label htmlFor="model">Model</Label>
            <Input
              id="model"
              data-testid="model-input"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              placeholder="e.g. claude-haiku-4-5-20251001 / gpt-5-codex"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-text-muted">
            <input
              type="checkbox"
              data-testid="resume-checkbox"
              checked={useResume}
              onChange={(e) => setUseResume(e.target.checked)}
              className="h-4 w-4 rounded border-border bg-bg-subtle text-accent focus:ring-accent"
            />
            Use <code className="text-text">--resume</code> when continuing a compatible run
          </label>

          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              onClick={() => save.mutate()}
              data-testid="settings-save"
              disabled={save.isPending}
            >
              {save.isPending ? "saving…" : "Save settings"}
            </Button>
            {savedNote ? (
              <span data-testid="settings-saved" className="text-xs text-status-succeeded">
                {savedNote}
              </span>
            ) : null}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Available harnesses</CardHeader>
        <CardBody>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="py-2">name</th>
                <th>resume</th>
                <th>raw JSON</th>
                <th>--model arg</th>
                <th>--resume arg</th>
              </tr>
            </thead>
            <tbody>
              {harnesses?.map((h) => (
                <tr key={h.name} className="border-t border-border">
                  <td className="py-2 font-mono text-text">{h.name}</td>
                  <td>{h.supports_resume ? "yes" : "no"}</td>
                  <td>{h.supports_raw_json ? "yes" : "no"}</td>
                  <td className="font-mono text-text-muted">{h.model_arg}</td>
                  <td className="font-mono text-text-muted">{h.resume_arg}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </div>
  );
}
