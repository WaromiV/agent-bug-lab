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
  | "prepare_agent"
  | "debater_pro"
  | "debater_con"
  | "judge_per_round"
  | "judge_final";

export type Status =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type ReviewerRole = "cleaner_agent" | "human";
export type Decision = "kept" | "removed" | "refined" | "needs_more_work";

export interface PrepareDossier {
  dossier: {
    summary: string;
    target_kind: string;
    scope_source_url: string;
    in_scope_targets: Array<{
      kind: string;
      name: string;
      url: string;
      why_in_scope: string;
      tech?: string;
    }>;
    prior_audits: Array<{
      source: string;
      year: string;
      url_or_citation: string;
      key_findings: string;
    }>;
    known_incidents: Array<{
      year: string;
      summary: string;
      severity: string;
      source_url: string;
    }>;
    attack_surfaces: Array<{
      name: string;
      category: string;
      description: string;
      evidence_targets: string[];
    }>;
    candidate_hotspots: Array<{
      target: string;
      area: string;
      score: number;
      reasons: string[];
      linked_surfaces: string[];
    }>;
    threat_model_notes: string[];
    open_questions: string[];
    severity_tiers?: Array<{
      name: string;
      qualifiers: string[];
      max_payout?: string;
    }>;
    out_of_scope?: string[];
    program_rules?: {
      poc_required?: boolean | null;
      kyc_required?: boolean | null;
      triaged_by?: string | null;
      primacy_of_impact?: boolean | null;
      custom_notes?: string[];
    };
  };
  saved_from_run_id: string;
}

export interface StaticFactsSummary {
  version: number;
  generated_at: string;
  language: string;
  build_system: string | null;
  build_ok: boolean;
  build_error: string | null;
  solc_root: string | null;
  solc_versions: string[];
  tool_versions: Record<string, string>;
  stats: {
    user_contracts?: number;
    external_functions?: number;
    callgraph_edges?: number;
    delegatecall_sinks?: number;
    storage_entries?: number;
  };
  contracts: Array<{
    name: string;
    path: string;
    is_abstract?: boolean;
    inherits?: string[];
    external_functions?: Array<{
      signature: string;
      visibility: string;
      mutability: string;
      modifiers: string[];
      is_constructor?: boolean;
    }>;
    modifier_definitions?: string[];
    delegatecall_sinks?: Array<{
      in_function: string;
      kind: string;
      file: string;
      line: number;
    }>;
    storage_layout?: Array<{ slot: number; offset?: number; label: string; type: string }>;
  }>;
  callgraph: { edges: Array<{ from: string; to: string }> };
  errors: string[];
}

export interface Project {
  id: string;
  name: string;
  bug_bounty_url: string;
  repo_path: string;
  prepare_dossier: PrepareDossier | null;
  prepare_run_id: string | null;
  static_facts: StaticFactsSummary | null;
  static_facts_generated_at: string | null;
  created_at: string;
}

export interface Scope {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
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
  prepare_run_id: string;
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
  effort: Effort | null;
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

export type Effort = "low" | "medium" | "high" | "xhigh" | "max";

export interface Settings {
  id: string;
  selected_harness: string;
  selected_model: string;
  secondary_model: string | null;
  secondary_harness: string | null;
  selected_effort: Effort;
  debate_max_rounds: number;
  use_resume_when_available: boolean;
  updated_at: string;
}

export interface SettingsPatch {
  selected_harness?: string;
  selected_model?: string;
  secondary_model?: string | null;
  secondary_harness?: string | null;
  selected_effort?: Effort;
  debate_max_rounds?: number;
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

// Debate (Microsoft MDASH-style pro/con/judge orchestration on a bug)
export type DebateStatus = "queued" | "running" | "finished" | "errored";
export type DebateSide = "pro" | "con" | "judge_note" | "judge_final";
export type DebateVerdict = "real" | "flawed" | "rejected";
export type DebateWinner = "pro" | "con" | "tie";

export interface DebateRead {
  id: string;
  bug_id: string;
  project_id: string;
  status: DebateStatus;
  max_rounds: number;
  current_round: number;
  primary_model: string;
  secondary_model: string;
  score: number | null;
  verdict: DebateVerdict | null;
  winning_side: DebateWinner | null;
  reasoning: string | null;
  key_unresolved: string[] | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface DebateTurnRead {
  id: string;
  round: number;
  side: DebateSide;
  run_id: string | null;
  payload: Record<string, unknown> | null;
  notes_md: string | null;
  created_at: string;
}

export interface DebateTranscript {
  debate: DebateRead;
  turns: DebateTurnRead[];
}

export interface DebateStartRequest {
  max_rounds?: number;
}
