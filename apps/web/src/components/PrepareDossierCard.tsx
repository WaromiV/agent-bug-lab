import { Link } from "react-router-dom";
import { ExternalLink, FileSearch, History, Target, Telescope } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import type { Project } from "@/lib/types";

interface Props {
  project: Project;
}

/**
 * Compact read-only dossier view on the project page. Surfaces the parts of
 * the recon-agent output most useful for kicking off a searcher: summary,
 * in-scope targets, top hotspots, attack surfaces, prior audits, known
 * incidents.
 */
export function PrepareDossierCard({ project }: Props) {
  const wrapper = project.prepare_dossier;
  if (!wrapper) {
    return (
      <Card>
        <CardHeader className="flex items-center gap-2">
          <FileSearch className="h-4 w-4 text-text-muted" />
          Recon dossier
        </CardHeader>
        <CardBody className="text-sm text-text-subtle">
          {project.prepare_run_id ? (
            <>
              Prepare run{" "}
              <Link
                to={`/projects/${project.id}/prepare`}
                className="text-accent hover:text-accent-hover font-mono text-xs"
              >
                {project.prepare_run_id}
              </Link>{" "}
              is still in flight or did not produce a dossier.
            </>
          ) : (
            "No prepare run yet."
          )}
        </CardBody>
      </Card>
    );
  }

  const { dossier } = wrapper;

  return (
    <Card data-testid="prepare-dossier-card">
      <CardHeader className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <Telescope className="h-4 w-4 text-text-muted" />
          Recon dossier
          <span className="ml-2 rounded-md border border-border bg-bg-subtle px-2 py-0.5 text-[10px] uppercase tracking-wide text-text-subtle">
            {dossier.target_kind}
          </span>
        </span>
        <span className="font-mono text-[11px] text-text-subtle">
          from{" "}
          <Link
            to={`/runs/${wrapper.saved_from_run_id}`}
            className="text-accent hover:text-accent-hover"
          >
            {wrapper.saved_from_run_id}
          </Link>
        </span>
      </CardHeader>
      <CardBody className="space-y-5">
        <p className="text-sm text-text leading-relaxed">{dossier.summary}</p>

        <div className="grid grid-cols-2 gap-3 text-xs text-text-muted md:grid-cols-4">
          <Stat label="in-scope targets" value={dossier.in_scope_targets.length.toString()} />
          <Stat label="prior audits" value={dossier.prior_audits.length.toString()} />
          <Stat label="known incidents" value={dossier.known_incidents.length.toString()} />
          <Stat label="hotspots" value={dossier.candidate_hotspots.length.toString()} />
        </div>

        <section>
          <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
            In-scope targets
          </div>
          <ul className="space-y-1.5">
            {dossier.in_scope_targets.map((t) => (
              <li key={t.name + t.url} className="text-xs">
                <div className="flex items-baseline gap-2">
                  <span className="rounded-sm bg-bg-subtle px-1.5 py-0.5 font-mono text-[10px] text-text-subtle">
                    {t.kind}
                  </span>
                  <span className="font-medium text-text">{t.name}</span>
                  {t.tech ? (
                    <span className="text-text-subtle">· {t.tech}</span>
                  ) : null}
                  {t.url ? (
                    <a
                      href={t.url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-1 inline-flex items-center gap-0.5 text-text-subtle hover:text-text"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : null}
                </div>
                {t.why_in_scope ? (
                  <div className="pl-2 text-text-subtle">{t.why_in_scope}</div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>

        <section>
          <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
            <Target className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
            Top hotspots
          </div>
          <ul className="space-y-1.5">
            {dossier.candidate_hotspots.slice(0, 10).map((h, i) => (
              <li
                key={`${h.target}-${h.area}-${i}`}
                className="flex items-baseline gap-2 text-xs"
              >
                <span className="w-10 shrink-0 text-right font-mono text-accent">
                  {h.score.toFixed(2)}
                </span>
                <span className="font-medium text-text">{h.target}</span>
                {h.area ? (
                  <span className="font-mono text-text-muted">· {h.area}</span>
                ) : null}
                <span className="text-text-subtle">
                  — {h.reasons.slice(0, 3).join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
            Attack surfaces
          </div>
          <div className="flex flex-wrap gap-1.5">
            {dossier.attack_surfaces.map((s) => (
              <span
                key={s.name}
                title={s.description}
                className="rounded-md border border-border bg-bg-subtle px-2 py-0.5 text-[11px] text-text-muted"
              >
                {s.name}
                <span className="ml-1.5 text-text-subtle">
                  ({s.evidence_targets.length})
                </span>
              </span>
            ))}
          </div>
        </section>

        {dossier.prior_audits.length > 0 ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
              Prior audits
            </div>
            <ul className="space-y-1 text-xs">
              {dossier.prior_audits.slice(0, 8).map((a, i) => (
                <li key={i}>
                  <span className="font-medium text-text">{a.source}</span>
                  {a.year ? (
                    <span className="ml-1 text-text-subtle">({a.year})</span>
                  ) : null}
                  {a.url_or_citation ? (
                    <>
                      {" — "}
                      <a
                        href={a.url_or_citation.startsWith("http") ? a.url_or_citation : undefined}
                        target="_blank"
                        rel="noreferrer"
                        className="text-accent hover:text-accent-hover break-all"
                      >
                        {a.url_or_citation}
                      </a>
                    </>
                  ) : null}
                  {a.key_findings ? (
                    <div className="pl-2 text-text-subtle">{a.key_findings}</div>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {dossier.known_incidents.length > 0 ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
              <History className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
              Known incidents
            </div>
            <ul className="space-y-1 text-xs">
              {dossier.known_incidents.slice(0, 8).map((inc, i) => (
                <li key={i}>
                  <span className="font-mono text-[10px] uppercase text-text-subtle">
                    {inc.severity}
                  </span>
                  {inc.year ? (
                    <span className="ml-1 text-text-subtle">{inc.year}</span>
                  ) : null}
                  {" — "}
                  <span className="text-text">{inc.summary}</span>
                  {inc.source_url ? (
                    <a
                      href={inc.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-1 inline-flex items-baseline gap-0.5 text-text-subtle hover:text-text"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {dossier.threat_model_notes.length > 0 ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
              Threat-model notes
            </div>
            <ul className="list-disc space-y-1 pl-5 text-xs text-text-muted">
              {dossier.threat_model_notes.slice(0, 8).map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {dossier.open_questions.length > 0 ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-yellow-500/80">
              Open questions
            </div>
            <ul className="list-disc space-y-1 pl-5 text-xs text-text-muted">
              {dossier.open_questions.slice(0, 8).map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {dossier.severity_tiers && dossier.severity_tiers.length > 0 ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
              Severity tiers (verbatim from bounty page)
            </div>
            <div className="space-y-2">
              {dossier.severity_tiers.map((t, i) => (
                <details key={i} className="rounded border border-border p-2">
                  <summary className="cursor-pointer text-xs font-medium text-text">
                    {t.name}
                    {t.max_payout ? (
                      <span className="ml-2 font-mono text-text-subtle">
                        · {t.max_payout}
                      </span>
                    ) : null}
                    <span className="ml-2 text-text-subtle">
                      · {t.qualifiers.length} qualifier{t.qualifiers.length === 1 ? "" : "s"}
                    </span>
                  </summary>
                  <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-text-muted">
                    {t.qualifiers.map((q, j) => (
                      <li key={j}>{q}</li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          </section>
        ) : null}

        {dossier.out_of_scope && dossier.out_of_scope.length > 0 ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
              Out-of-scope clauses (verbatim, {dossier.out_of_scope.length})
            </div>
            <details className="rounded border border-border p-2">
              <summary className="cursor-pointer text-xs text-text-muted">
                show all
              </summary>
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-text-muted">
                {dossier.out_of_scope.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </details>
          </section>
        ) : null}

        {dossier.program_rules ? (
          <section>
            <div className="mb-2 text-xs uppercase tracking-wide text-text-subtle">
              Program rules
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
              <RuleChip label="PoC required" value={dossier.program_rules.poc_required} />
              <RuleChip label="KYC required" value={dossier.program_rules.kyc_required} />
              <RuleChip
                label="Primacy of impact"
                value={dossier.program_rules.primacy_of_impact}
              />
              <div>
                <div className="text-[10px] uppercase tracking-wide text-text-subtle">
                  Triaged by
                </div>
                <div className="font-mono text-xs text-text">
                  {dossier.program_rules.triaged_by ?? "—"}
                </div>
              </div>
            </div>
            {dossier.program_rules.custom_notes && dossier.program_rules.custom_notes.length > 0 ? (
              <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-text-muted">
                {dossier.program_rules.custom_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}
      </CardBody>
    </Card>
  );
}

function RuleChip({ label, value }: { label: string; value: boolean | null | undefined }) {
  const display = value === true ? "yes" : value === false ? "no" : "—";
  const color =
    value === true
      ? "text-status-succeeded"
      : value === false
      ? "text-text-subtle"
      : "text-text-subtle";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-text-subtle">{label}</div>
      <div className={`font-mono text-xs ${color}`}>{display}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-text-subtle">
        {label}
      </div>
      <div className="font-mono text-sm text-text">{value}</div>
    </div>
  );
}
