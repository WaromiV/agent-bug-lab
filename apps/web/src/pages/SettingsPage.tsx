import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Effort } from "@/lib/types";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

const effortOptions = [
  { label: "low",    value: "low" },
  { label: "medium", value: "medium" },
  { label: "high",   value: "high" },
  { label: "xhigh",  value: "xhigh" },
  { label: "max",    value: "max" },
];

export function SettingsPage() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const { data: harnesses } = useQuery({
    queryKey: ["harnesses"],
    queryFn: api.listHarnesses,
  });

  const [selectedHarness, setSelectedHarness] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [secondaryModel, setSecondaryModel] = useState("");
  const [secondaryHarness, setSecondaryHarness] = useState("");
  const [selectedEffort, setSelectedEffort] = useState<Effort>("max");
  const [debateRounds, setDebateRounds] = useState<number>(3);
  const [useResume, setUseResume] = useState(true);
  const [savedNote, setSavedNote] = useState<string | null>(null);

  useEffect(() => {
    if (settings) {
      setSelectedHarness(settings.selected_harness);
      setSelectedModel(settings.selected_model);
      setSecondaryModel(settings.secondary_model ?? "");
      setSecondaryHarness(settings.secondary_harness ?? "");
      setSelectedEffort(settings.selected_effort);
      setDebateRounds(settings.debate_max_rounds);
      setUseResume(settings.use_resume_when_available);
    }
  }, [settings]);

  const save = useMutation({
    mutationFn: () =>
      api.patchSettings({
        selected_harness: selectedHarness,
        selected_model: selectedModel,
        secondary_model: secondaryModel.trim() === "" ? null : secondaryModel.trim(),
        secondary_harness: secondaryHarness.trim() === "" ? null : secondaryHarness.trim(),
        selected_effort: selectedEffort,
        debate_max_rounds: debateRounds,
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
            <Label htmlFor="model">Primary model</Label>
            <Input
              id="model"
              data-testid="model-input"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              placeholder="e.g. claude-opus-4-7 / claude-haiku-4-5-20251001 / gpt-5-codex"
            />
            <p className="mt-1 text-xs text-text-subtle">
              Used by searcher, cleaner, prepare, debater_pro, and the judge.
            </p>
          </div>
          <div>
            <Label htmlFor="secondary-model">Secondary model (debate-debunk)</Label>
            <Input
              id="secondary-model"
              data-testid="secondary-model-input"
              value={secondaryModel}
              onChange={(e) => setSecondaryModel(e.target.value)}
              placeholder="leave empty to use primary"
            />
            <p className="mt-1 text-xs text-text-subtle">
              Used only by debater_con — the counterpoint side that tries to break
              the bug. Microsoft's MDASH spec uses a separate model for the
              refuter; empty falls back to primary.
            </p>
          </div>
          <div>
            <Label htmlFor="secondary-harness">Secondary harness (debate-debunk)</Label>
            <Select
              id="secondary-harness"
              data-testid="secondary-harness-select"
              value={secondaryHarness}
              onChange={(e) => setSecondaryHarness(e.target.value)}
              options={[
                { label: "(use primary)", value: "" },
                ...(harnesses ? harnesses.map((h) => ({ label: h.name, value: h.name })) : []),
              ]}
            />
            <p className="mt-1 text-xs text-text-subtle">
              CLI used to invoke the secondary model — set when secondary model
              belongs to a different vendor than the primary
              (e.g. primary <code className="text-text-muted">claude_code</code>,
              secondary <code className="text-text-muted">codex</code>).
              Empty = same harness as primary.
            </p>
          </div>
          <div>
            <Label htmlFor="effort">Reasoning effort</Label>
            <Select
              id="effort"
              data-testid="effort-select"
              value={selectedEffort}
              onChange={(e) => setSelectedEffort(e.target.value as Effort)}
              options={effortOptions}
            />
            <p className="mt-1 text-xs text-text-subtle">
              Higher effort = deeper reasoning + bigger cost / longer runs. Claude
              Code maps this to <code className="text-text-muted">--effort</code>.
              Codex ignores it (configure via <code className="text-text-muted">~/.codex/config.toml</code>).
            </p>
          </div>
          <div>
            <Label htmlFor="debate-rounds">Debate rounds (N)</Label>
            <Input
              id="debate-rounds"
              data-testid="debate-rounds-input"
              type="number"
              min={1}
              max={20}
              value={debateRounds}
              onChange={(e) => setDebateRounds(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            />
            <p className="mt-1 text-xs text-text-subtle">
              Every debate runs EXACTLY this many rounds. Per-round judge cannot
              halt early. Higher N = deeper rebuttal cycles + bigger cost.
            </p>
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
