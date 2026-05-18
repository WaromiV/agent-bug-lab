import clsx from "clsx";
import { Badge } from "./ui/Badge";
import type { Severity } from "@/lib/types";

const colors: Record<Severity, string> = {
  critical: "bg-sev-critical/15 text-sev-critical border border-sev-critical/30",
  high:     "bg-sev-high/15 text-sev-high border border-sev-high/30",
  medium:   "bg-sev-medium/15 text-sev-medium border border-sev-medium/30",
  low:      "bg-sev-low/15 text-sev-low border border-sev-low/30",
  info:     "bg-sev-info/15 text-sev-info border border-sev-info/30",
  unknown:  "bg-sev-unknown/15 text-sev-unknown border border-sev-unknown/30",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge className={clsx(colors[severity], "uppercase tracking-wide")}>{severity}</Badge>;
}
