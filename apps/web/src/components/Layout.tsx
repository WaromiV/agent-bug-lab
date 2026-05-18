import { NavLink, Outlet } from "react-router-dom";
import clsx from "clsx";
import {
  BarChart3,
  Bug as BugIcon,
  CircuitBoard,
  FolderGit2,
  ListChecks,
  Settings as SettingsIcon,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const navItems = [
  { to: "/projects",      label: "Projects",     icon: FolderGit2 },
  { to: "/runs",          label: "Runs",         icon: CircuitBoard },
  { to: "/bugs",          label: "Bugs",         icon: BugIcon },
  { to: "/review-queue",  label: "Review queue", icon: ListChecks },
  { to: "/settings",      label: "Settings",     icon: SettingsIcon },
];

export function Layout() {
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5000,
  });
  return (
    <div className="flex h-full min-h-screen bg-bg text-text">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-bg-panel">
        <div className="border-b border-border px-4 py-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-accent" />
            <span className="font-semibold">agent-bug-lab</span>
          </div>
          <div className="mt-1 text-xs text-text-subtle" data-testid="api-health">
            api {health?.status ?? "…"}
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-2 py-3">
          {navItems.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition",
                  isActive
                    ? "bg-bg-hover text-text"
                    : "text-text-muted hover:bg-bg-hover hover:text-text",
                )
              }
            >
              <n.icon className="h-4 w-4" />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border px-3 py-3 text-xs text-text-subtle">
          <div data-testid="harness-readout">
            harness: <span className="text-text">{settings?.selected_harness ?? "…"}</span>
          </div>
          <div data-testid="model-readout">
            model: <span className="text-text">{settings?.selected_model ?? "…"}</span>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
