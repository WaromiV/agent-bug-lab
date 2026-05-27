import type { DebateRead } from "@/lib/types";

/**
 * Renders the judge's final score (0..10) as a colored chip on a red→amber→
 * green gradient. While a debate is running, shows the round counter. While
 * errored, shows ERR.
 */
export function DebateChip({ debate }: { debate: DebateRead | null | undefined }) {
  if (!debate) return null;

  if (debate.status === "running" || debate.status === "queued") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-subtle px-1.5 py-0.5 text-[10px] font-mono text-text-muted"
        title={`debate ${debate.status} — round ${debate.current_round}/${debate.max_rounds}`}
        data-testid={`debate-chip-${debate.bug_id}`}
      >
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
        debate {debate.current_round}/{debate.max_rounds}
      </span>
    );
  }
  if (debate.status === "errored") {
    return (
      <span
        className="inline-flex items-center rounded-md border border-status-failed/40 bg-status-failed/10 px-1.5 py-0.5 text-[10px] font-mono text-status-failed"
        title={debate.error ?? "debate errored"}
        data-testid={`debate-chip-${debate.bug_id}`}
      >
        debate ERR
      </span>
    );
  }

  // finished — color by score 0..10
  const score = debate.score ?? 0;
  const hue = Math.round((score / 10) * 120); // 0=red, 60=amber, 120=green
  const style = {
    backgroundColor: `hsl(${hue} 70% 18%)`,
    borderColor: `hsl(${hue} 70% 32%)`,
    color: `hsl(${hue} 90% 80%)`,
  } as const;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-mono"
      style={style}
      title={`judge: ${debate.verdict} · winner=${debate.winning_side} · score ${score}/10`}
      data-testid={`debate-chip-${debate.bug_id}`}
    >
      <span className="font-semibold">{score}/10</span>
      <span className="opacity-70">{debate.verdict}</span>
    </span>
  );
}
