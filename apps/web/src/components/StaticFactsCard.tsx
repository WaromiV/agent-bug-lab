import { useState } from "react";
import { ChevronDown, ChevronRight, FlaskConical, AlertTriangle } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import type { Project } from "@/lib/types";
import { fmtDateTime } from "@/lib/format";

interface Props {
  project: Project;
}

/**
 * Compact read-only view of the project's static_facts pass (slither +
 * forge inspect). Counts only — for the raw payload, agents read it from
 * <data_dir>/static_facts/facts.json.
 */
export function StaticFactsCard({ project }: Props) {
  const facts = project.static_facts;
  const [open, setOpen] = useState(false);

  if (!facts) {
    return (
      <Card>
        <CardHeader className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-text-muted" />
          Static facts
        </CardHeader>
        <CardBody className="text-sm text-text-subtle">
          No static-facts pass yet. Will run automatically on the next prepare
          run if the target is a Solidity project.
        </CardBody>
      </Card>
    );
  }

  const s = facts.stats || {};
  const hasErrors = facts.errors && facts.errors.length > 0;

  return (
    <Card>
      <CardHeader className="flex items-center gap-2">
        <FlaskConical className="h-4 w-4 text-text-muted" />
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1 text-left hover:text-accent"
          data-testid="static-facts-toggle"
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Static facts
        </button>
        <span className="ml-auto text-xs text-text-subtle">
          {facts.build_ok ? "build ok" : "build failed"} ·{" "}
          {project.static_facts_generated_at
            ? fmtDateTime(project.static_facts_generated_at)
            : "n/a"}
        </span>
      </CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-5">
          <Stat label="contracts" value={s.user_contracts} />
          <Stat label="external fns" value={s.external_functions} />
          <Stat label="callgraph edges" value={s.callgraph_edges} />
          <Stat label="delegatecall sinks" value={s.delegatecall_sinks} />
          <Stat label="storage entries" value={s.storage_entries} />
        </div>
        <div className="mt-3 text-xs text-text-subtle">
          {facts.solc_root && facts.solc_root !== "." ? (
            <>solidity sub-project: <span className="font-mono">{facts.solc_root}</span> · </>
          ) : null}
          solc: {facts.solc_versions?.join(", ") || "n/a"} ·{" "}
          tools: {Object.entries(facts.tool_versions || {})
            .map(([k, v]) => `${k} ${v}`)
            .join(", ")}
        </div>
        {hasErrors ? (
          <div className="mt-3 flex items-start gap-2 rounded border border-status-failed/50 bg-status-failed/10 p-2 text-xs">
            <AlertTriangle className="h-4 w-4 text-status-failed shrink-0" />
            <ul className="space-y-1">
              {facts.errors.slice(0, 6).map((e, i) => (
                <li key={i} className="font-mono">{e}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {open ? (
          <div className="mt-4 space-y-3 text-xs">
            {facts.contracts.slice(0, 30).map((c) => (
              <details key={c.path + ":" + c.name} className="rounded border border-border p-2">
                <summary className="cursor-pointer font-mono text-sm text-text">
                  {c.name}{" "}
                  <span className="text-text-subtle">({c.path})</span>{" "}
                  <span className="text-text-subtle">
                    · {c.external_functions?.length ?? 0} fns
                    {c.delegatecall_sinks && c.delegatecall_sinks.length > 0
                      ? ` · ${c.delegatecall_sinks.length} delegatecall`
                      : ""}
                  </span>
                </summary>
                <div className="mt-2 space-y-2">
                  {c.inherits && c.inherits.length > 0 ? (
                    <div>
                      <span className="text-text-subtle">inherits:</span>{" "}
                      <span className="font-mono">{c.inherits.join(", ")}</span>
                    </div>
                  ) : null}
                  {c.modifier_definitions && c.modifier_definitions.length > 0 ? (
                    <div>
                      <span className="text-text-subtle">modifiers:</span>{" "}
                      <span className="font-mono">
                        {c.modifier_definitions.join(", ")}
                      </span>
                    </div>
                  ) : null}
                  {c.delegatecall_sinks && c.delegatecall_sinks.length > 0 ? (
                    <div>
                      <div className="text-text-subtle">delegatecall sinks:</div>
                      <ul className="ml-3 space-y-0.5 font-mono">
                        {c.delegatecall_sinks.map((d, i) => (
                          <li key={i}>
                            {d.kind} in {d.in_function} @ {d.file}:{d.line}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {c.external_functions && c.external_functions.length > 0 ? (
                    <div>
                      <div className="text-text-subtle">external surface:</div>
                      <ul className="ml-3 space-y-0.5 font-mono">
                        {c.external_functions.slice(0, 20).map((f, i) => (
                          <li key={i}>
                            {f.signature}{" "}
                            <span className="text-text-subtle">
                              [{f.visibility} · {f.mutability}
                              {f.modifiers && f.modifiers.length > 0
                                ? " · " + f.modifiers.join(",")
                                : ""}
                              ]
                            </span>
                          </li>
                        ))}
                        {c.external_functions.length > 20 ? (
                          <li className="text-text-subtle">
                            … +{c.external_functions.length - 20} more
                          </li>
                        ) : null}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </details>
            ))}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <div className="text-2xl font-semibold tabular-nums">{value ?? "—"}</div>
      <div className="text-xs uppercase tracking-wide text-text-muted">{label}</div>
    </div>
  );
}
