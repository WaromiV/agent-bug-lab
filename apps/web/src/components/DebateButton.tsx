import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Swords } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { DebateChip } from "./DebateChip";

/**
 * ⚔ Debate run — starts a multi-turn debate on this bug. Polls every 2s
 * while the debate is queued/running; the chip beside it switches from
 * round-counter to a colored score when the judge writes the final verdict.
 */
export function DebateButton({
  bugId,
  size = "sm",
}: {
  bugId: string;
  size?: "sm" | "md";
}) {
  const qc = useQueryClient();
  const { data: transcript } = useQuery({
    queryKey: ["debate", bugId],
    queryFn: () => api.getDebate(bugId),
    refetchInterval: (q) => {
      const s = q.state.data?.debate.status;
      return s === "queued" || s === "running" ? 2000 : false;
    },
  });
  const debate = transcript?.debate ?? null;
  const running = debate?.status === "queued" || debate?.status === "running";

  const start = useMutation({
    mutationFn: () => api.startDebate(bugId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["debate", bugId] });
    },
  });

  return (
    <div className="inline-flex items-center gap-2">
      <Button
        variant={debate ? "outline" : "primary"}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          start.mutate();
        }}
        disabled={running || start.isPending}
        data-testid={`debate-button-${bugId}`}
        size={size}
      >
        <Swords className="h-3.5 w-3.5" />
        {running ? "debating…" : debate ? "Debate again" : "Debate run"}
      </Button>
      <DebateChip debate={debate} />
    </div>
  );
}
