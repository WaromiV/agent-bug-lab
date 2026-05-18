export type Severity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "info"
  | "unknown";

export type Role =
  | "searcher_agent"
  | "cleaner_agent"
  | "critical_thinking_agent";

export type Status =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type ReviewerRole = "cleaner_agent" | "critical_thinking_agent" | "human";
export type Decision = "kept" | "removed" | "refined" | "needs_more_work";

export interface Project {
  id: string;
  name: string;
  bug_bounty_url: string;
  repo_path: string;
  created_at: string;
}

export interface Scope {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
  is_preliminary: boolean;
}

export interface ScopeCreate {
  name: string;
  description?: string | null;
}

export interface ScopePatch {
  name?: string;
  description?: string | null;
}

export interface ProjectCreate {
  name: string;
  bug_bounty_url: string;
}

export interface ProjectCreateResponse {
  project: Project;
  searcher_run_id: string;
}

export interface Bug {
  id: string;
  severity: Severity;
  scope_id: string;
  description: string;
  repro_path: string;
  repro_usage: string;
  missing_for_full_chain: string;
  scope_name?: string | null;
  project_id?: string | null;
}

export interface BugListItem extends Bug {
  scope_name: string | null;
  project_id: string | null;
  last_reviewed_at: string | null;
  last_decision: Decision | null;
}

export interface BugPatch {
  severity?: Severity;
  scope_id?: string;
  description?: string;
  repro_path?: string;
  repro_usage?: string;
  missing_for_full_chain?: string;
}

export interface Run {
  id: string;
  project_id: string;
  role: Role;
  harness: string;
  model: string;
  status: Status;
  objective: string;
  resume_from_run_id: string | null;
  harness_session_id: string | null;
  data_dir: string;
  started_at: string | null;
  finished_at: string | null;
  raw_input: Record<string, unknown>;
  raw_output: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
}

export interface AgentLogRow {
  id: number;
  run_id: string;
  level: "debug" | "info" | "warning" | "error";
  message: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface Settings {
  id: string;
  selected_harness: string;
  selected_model: string;
  use_resume_when_available: boolean;
  updated_at: string;
}

export interface SettingsPatch {
  selected_harness?: string;
  selected_model?: string;
  use_resume_when_available?: boolean;
}

export interface Harness {
  name: string;
  supports_resume: boolean;
  supports_raw_json: boolean;
  model_arg: string;
  resume_arg: string;
}

export interface CleanRequest {
  bug_ids: string[];
}

export interface CriticalRequest {
  bug_id: string;
}
