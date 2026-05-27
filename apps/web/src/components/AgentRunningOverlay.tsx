import { Loader2 } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";

interface Props {
  title: string;
  description: ReactNode;
  expectedHint: string;
  testId?: string;
}

/**
 * Full-viewport modal shown while a synchronous agent run is in flight
 * (export / dedup / future curation passes). Owns the elapsed-seconds
 * counter so callers don't have to.
 */
export function AgentRunningOverlay({ title, description, expectedHint, testId }: Props) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg/90 backdrop-blur-sm"
      data-testid={testId}
      role="dialog"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="w-96 max-w-[90vw] rounded-lg border border-border bg-bg-panel p-6 shadow-xl">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-accent" />
          <div className="text-sm font-semibold text-text">{title}</div>
        </div>
        <div className="mt-3 text-xs text-text-muted leading-relaxed">{description}</div>
        <div className="mt-4 flex items-center justify-between text-[11px] text-text-subtle font-mono">
          <span>
            elapsed {Math.floor(elapsed / 60)}m {String(elapsed % 60).padStart(2, "0")}s
          </span>
          <span>{expectedHint}</span>
        </div>
      </div>
    </div>
  );
}
