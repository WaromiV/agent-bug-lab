import clsx from "clsx";
import { Badge } from "./ui/Badge";
import type { Status } from "@/lib/types";

const colors: Record<Status, string> = {
  queued:    "bg-status-queued/15 text-status-queued border border-status-queued/30",
  running:   "bg-status-running/15 text-status-running border border-status-running/30 animate-pulse",
  succeeded: "bg-status-succeeded/15 text-status-succeeded border border-status-succeeded/30",
  failed:    "bg-status-failed/15 text-status-failed border border-status-failed/30",
  cancelled: "bg-status-cancelled/15 text-status-cancelled border border-status-cancelled/30",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <Badge className={clsx(colors[status], "uppercase tracking-wide")}>
      {status}
    </Badge>
  );
}
