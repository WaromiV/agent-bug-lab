import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { DebateChip } from "./DebateChip";
import type { DebateTurnRead } from "@/lib/types";

/**
 * Full debate transcript card for a bug:
 *   header   — judge's final score chip + verdict + winning side
 *   per-round Markdown columns of pro / con / judge_note
 *   final reasoning + key_unresolved
 *
 * Polls every 2s while running so the UI fills in turn by turn.
 */
export function DebateTranscriptCard({ bugId }: { bugId: string }) {
  const { data: transcript } = useQuery({
    queryKey: ["debate", bugId],
    queryFn: () => api.getDebate(bugId),
    refetchInterval: (q) => {
      const s = q.state.data?.debate.status;
      return s === "queued" || s === "running" ? 2000 : false;
    },
  });

  if (!transcript) {
    return (
      <Card>
        <CardHeader>Debate</CardHeader>
        <CardBody>
          <div className="text-sm text-text-subtle">No debate yet. Click "Debate run" above.</div>
        </CardBody>
      </Card>
    );
  }

  const { debate, turns } = transcript;
  const byRound = new Map<number, { pro?: DebateTurnRead; con?: DebateTurnRead; judge_note?: DebateTurnRead }>();
  let finalTurn: DebateTurnRead | null = null;
  for (const t of turns) {
    if (t.side === "judge_final") {
      finalTurn = t;
      continue;
    }
    const r = byRound.get(t.round) ?? {};
    if (t.side === "pro" || t.side === "con" || t.side === "judge_note") {
      r[t.side] = t;
    }
    byRound.set(t.round, r);
  }

  const sortedRounds = Array.from(byRound.keys()).sort((a, b) => a - b);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <span className="flex-1">Debate transcript</span>
          <DebateChip debate={debate} />
          <span className="text-xs text-text-subtle">
            pro={debate.primary_model} · con={debate.secondary_model}
          </span>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {debate.status === "errored" ? (
          <div className="rounded border border-status-failed/40 bg-status-failed/10 p-3 text-xs text-status-failed">
            {debate.error ?? "errored"}
          </div>
        ) : null}

        {sortedRounds.map((round) => {
          const r = byRound.get(round)!;
          return (
            <div key={round} className="rounded border border-border bg-bg-subtle">
              <div className="flex items-center justify-between border-b border-border px-3 py-1.5 text-xs uppercase tracking-wide text-text-muted">
                <span>Round {round}/{debate.max_rounds}</span>
              </div>
              <div className="grid grid-cols-1 gap-3 p-3 md:grid-cols-2">
                <ArgPanel side="pro" turn={r.pro} />
                <ArgPanel side="con" turn={r.con} />
              </div>
              {r.judge_note ? (
                <div className="border-t border-border bg-bg-panel p-3 text-xs text-text-muted">
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-text-subtle">judge notes</div>
                  <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed">
                    {r.judge_note.notes_md ?? "(no notes)"}
                  </pre>
                </div>
              ) : null}
            </div>
          );
        })}

        {finalTurn && debate.status === "finished" ? (
          <div className="rounded border border-border bg-bg-subtle p-3">
            <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-text-muted">
              <span>Final verdict</span>
              <DebateChip debate={debate} />
              <span>winner: {debate.winning_side}</span>
            </div>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-text">
              {debate.reasoning ?? "(no reasoning)"}
            </pre>
            {debate.key_unresolved && debate.key_unresolved.length > 0 ? (
              <div className="mt-3 border-t border-border pt-2 text-xs">
                <div className="mb-1 uppercase tracking-wide text-text-subtle">Key unresolved</div>
                <ul className="list-disc space-y-1 pl-5 text-text-muted">
                  {debate.key_unresolved.map((k, i) => (
                    <li key={i}>{k}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ArgPanel({ side, turn }: { side: "pro" | "con"; turn: DebateTurnRead | undefined }) {
  const label = side === "pro" ? "PRO — champion" : "CON — refuter";
  const sideTint = side === "pro" ? "border-status-succeeded/30" : "border-status-failed/30";

  if (!turn) {
    return (
      <div className={`rounded border bg-bg-panel p-2 text-xs text-text-subtle ${sideTint}`}>
        <div className="mb-1 font-semibold uppercase tracking-wide text-text-muted">{label}</div>
        <div>(waiting)</div>
      </div>
    );
  }
  const p = (turn.payload ?? {}) as Record<string, unknown>;
  const claim = (p.claim ?? p.strongest_refutation ?? "—") as string;
  const evidence = Array.isArray(p.key_evidence)
    ? (p.key_evidence as Array<Record<string, unknown>>)
    : [];
  const addressed = Array.isArray(p.addressed_opponent_points)
    ? (p.addressed_opponent_points as string[])
    : [];

  return (
    <div className={`rounded border bg-bg-panel p-2 text-xs ${sideTint}`}>
      <div className="mb-1 flex items-center gap-2">
        <span className="font-semibold uppercase tracking-wide text-text-muted">{label}</span>
        {turn.run_id ? (
          <Link
            to={`/runs/${turn.run_id}`}
            className="font-mono text-[10px] text-text-subtle hover:text-text"
          >
            {turn.run_id}
          </Link>
        ) : null}
      </div>
      <div className="mb-2 text-text">{claim}</div>

      {evidence.length > 0 ? (
        <div className="mb-2">
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-text-subtle">evidence</div>
          <ul className="space-y-1">
            {evidence.map((e, i) => (
              <li key={i} className="text-text-muted">
                <span className="rounded bg-bg-subtle px-1 py-0.5 font-mono text-[10px]">
                  {String(e.kind ?? "?")}
                </span>{" "}
                <span className="font-mono">{String(e.citation ?? "")}</span>
                {e.quote ? (
                  <pre className="mt-0.5 whitespace-pre-wrap font-mono text-[10px] text-text-subtle">
                    {String(e.quote).slice(0, 240)}
                  </pre>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {addressed.length > 0 ? (
        <div>
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-text-subtle">
            addressed opponent
          </div>
          <ul className="list-disc space-y-1 pl-4 text-text-muted">
            {addressed.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
