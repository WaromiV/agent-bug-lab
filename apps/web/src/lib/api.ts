import type {
  AgentLogRow,
  Bug,
  BugListItem,
  BugPatch,
  CleanRequest,
  DebateRead,
  DebateStartRequest,
  DebateTranscript,
  Harness,
  Project,
  ProjectCreate,
  ProjectCreateResponse,
  Run,
  Scope,
  ScopeCreate,
  ScopePatch,
  Settings,
  SettingsPatch,
  Status,
} from "./types";

const BASE = "/api";

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`API ${status}: ${JSON.stringify(detail)}`);
  }
}

export const api = {
  health: () => fetch("/health").then((r) => r.json()),

  // ── projects ──
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (body: ProjectCreate) =>
    request<ProjectCreateResponse>("/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: "DELETE" }),
  startSearcher: (id: string, count: number = 1) =>
    request<{ run_ids: string[]; count: number }>(
      `/projects/${id}/start-searcher?count=${count}`,
      { method: "POST" },
    ),
  dedupProject: (id: string) =>
    request<{
      groups_count: number;
      deleted_count: number;
      candidates_seen: number;
      groups: { canonical: string; duplicates: string[]; reason: string }[];
      deleted_bug_ids: string[];
      kept_canonical_ids: string[];
      model_summary: string;
      data_dir: string;
    }>(`/projects/${id}/dedup`, { method: "POST" }),
  exportProject: async (
    id: string,
  ): Promise<{ blob: Blob; filename: string }> => {
    const res = await fetch(`${BASE}/projects/${id}/export`, { method: "POST" });
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = await res.json();
      } catch {
        detail = await res.text();
      }
      throw new ApiError(res.status, detail);
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const m = /filename="([^"]+)"/i.exec(cd);
    const filename = m?.[1] || `findings_${id}.md`;
    return { blob, filename };
  },

  // ── runs ──
  listRuns: (params: { project_id?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.project_id) qs.set("project_id", params.project_id);
    if (params.limit) qs.set("limit", String(params.limit));
    const tail = qs.toString();
    return request<Run[]>(`/runs${tail ? `?${tail}` : ""}`);
  },
  getRun: (id: string) => request<Run>(`/runs/${id}`),
  cancelRun: (id: string) =>
    request<Run>(`/runs/${id}/cancel`, { method: "POST" }),
  resumeRun: (id: string) =>
    request<Run>(`/runs/${id}/resume`, { method: "POST" }),
  listRunLogs: (id: string, after_id?: number, limit = 500) => {
    const qs = new URLSearchParams();
    if (after_id !== undefined) qs.set("after_id", String(after_id));
    qs.set("limit", String(limit));
    return request<AgentLogRow[]>(`/runs/${id}/logs?${qs}`);
  },

  // ── scopes ──
  listScopes: (project_id: string) =>
    request<Scope[]>(`/projects/${project_id}/scopes`),
  createScope: (project_id: string, body: ScopeCreate) =>
    request<Scope>(`/projects/${project_id}/scopes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchScope: (scope_id: string, body: ScopePatch) =>
    request<Scope>(`/scopes/${scope_id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // ── bugs ──
  listBugs: (params: {
    project_id?: string;
    scope_id?: string;
    severity?: string;
    search?: string;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.project_id) qs.set("project_id", params.project_id);
    if (params.scope_id) qs.set("scope_id", params.scope_id);
    if (params.severity) qs.set("severity", params.severity);
    if (params.search) qs.set("search", params.search);
    const tail = qs.toString();
    return request<BugListItem[]>(`/bugs${tail ? `?${tail}` : ""}`);
  },
  getBug: (id: string) => request<Bug>(`/bugs/${id}`),
  patchBug: (id: string, body: BugPatch) =>
    request<Bug>(`/bugs/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteBug: (id: string) =>
    request<void>(`/bugs/${id}`, { method: "DELETE" }),
  exportBugs: (project_id?: string) => {
    const qs = project_id ? `?project_id=${encodeURIComponent(project_id)}` : "";
    return request<Bug[]>(`/bugs/export${qs}`, { method: "POST" });
  },

  // ── review queue ──
  reviewQueue: (project_id?: string) => {
    const qs = project_id ? `?project_id=${encodeURIComponent(project_id)}` : "";
    return request<BugListItem[]>(`/review-queue${qs}`);
  },
  runCleaner: (body: CleanRequest) =>
    request<Run>("/review-queue/clean", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ── debates ──
  startDebate: (bugId: string, body: DebateStartRequest = {}) =>
    request<DebateRead>(`/bugs/${bugId}/debate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getDebate: (bugId: string) =>
    request<DebateTranscript | null>(`/bugs/${bugId}/debate`),

  // ── settings ──
  getSettings: () => request<Settings>("/settings"),
  patchSettings: (body: SettingsPatch) =>
    request<Settings>("/settings", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // ── harnesses ──
  listHarnesses: () => request<Harness[]>("/harnesses"),
};

/** Server-pushed events on `/api/runs/{id}/ws`. */
export type RunEvent =
  | { kind: "run"; run: Run }
  | { kind: "log"; row: AgentLogRow }
  | { kind: "tick"; now: string }
  | { kind: "end"; status: Status }
  | { kind: "error"; error: string };

/** Open a WebSocket on `/api/runs/{id}/ws`; returns a closer fn. */
export function subscribeRun(
  runId: string,
  onEvent: (e: RunEvent) => void,
): () => void {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/api/runs/${runId}/ws`;
  const ws = new WebSocket(url);
  ws.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data));
    } catch {
      /* ignore non-JSON frames */
    }
  };
  return () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close();
    }
  };
}
