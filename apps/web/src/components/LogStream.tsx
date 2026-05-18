import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import type { AgentLogRow } from "@/lib/types";

const levelColor: Record<string, string> = {
  debug: "text-text-subtle",
  info: "text-text-muted",
  warning: "text-yellow-400",
  error: "text-red-400",
};

interface Props {
  rows: AgentLogRow[];
  className?: string;
}

/**
 * Pure display: takes log rows in, renders them with sticky-bottom autoscroll.
 * The WebSocket subscription lives in `useRunStream` so the page owns one
 * connection for run state + logs + ticks.
 */
export function LogStream({ rows, className }: Props) {
  const [autoscroll, setAutoscroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoscroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [rows, autoscroll]);

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setAutoscroll(near);
  };

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      data-testid="log-stream"
      className={clsx(
        "scrollbar-thin h-96 overflow-y-auto rounded-md border border-border bg-bg-subtle p-3 font-mono text-xs",
        className,
      )}
    >
      {rows.length === 0 ? (
        <div className="text-text-subtle">No logs yet…</div>
      ) : (
        rows.map((r) => (
          <div key={r.id} className="flex gap-2 py-0.5">
            <span className="shrink-0 text-text-subtle">
              {new Date(r.created_at).toLocaleTimeString()}
            </span>
            <span
              className={clsx(
                "shrink-0 uppercase",
                levelColor[r.level] || "text-text-muted",
              )}
            >
              {r.level}
            </span>
            <span className="break-all text-text">{r.message}</span>
            {r.payload ? (
              <span className="text-text-subtle">{JSON.stringify(r.payload)}</span>
            ) : null}
          </div>
        ))
      )}
    </div>
  );
}
