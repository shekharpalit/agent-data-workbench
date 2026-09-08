import type {
  GradeStatus,
  Json,
  ReviewStatus,
  TaskSpec,
  Trial,
} from "./contracts";
export interface Review {
  status: ReviewStatus;
  reviewer?: string;
  note: string;
  at?: string;
}
export interface Versioned<T> {
  id: string;
  spec: T;
  revision: number;
  sha256: string;
  created_at: string;
  previous: { id: string; sha256: string } | null;
  review: Review;
}
export interface WorldSpec {
  name: string;
  domain: string;
  description: string;
  schemas: Record<string, Record<string, Json>>;
  tools: {
    name: string;
    description: string;
    input_schema: Record<string, Json>;
    output_schema: Record<string, Json>;
  }[];
  relationships: string[];
  permissions: string[];
  invariants: string[];
  sources: string[];
  unresolved_questions: string[];
}
export type World = Omit<Versioned<WorldSpec>, "previous"> & {
  previous_id: string | null;
  previous_sha256: string | null;
};
export interface Capability {
  id: string;
  name: string;
  description: string;
  required_slices: string[];
}
export interface TaxonomySpec {
  name: string;
  description: string;
  capabilities: Capability[];
}
export type Taxonomy = Versioned<TaxonomySpec>;
export interface CoverageMapping {
  kind: "trace" | "task";
  entity_id: string;
  capability_id: string;
  slice: string;
  rationale: string;
  source: string;
  reviewer: string;
}
export interface CoverageMetrics {
  traces: number;
  task_versions: number;
  accepted_tasks: number;
  tested_task_versions: number;
  unexecuted_task_versions: number;
  trial_results: Record<GradeStatus, number>;
  all_observed_valid_attempts_passed: boolean;
  independent_trace_groups: number;
}
export interface BehavioralCoverage {
  taxonomy_id: string;
  taxonomy_sha256: string;
  taxonomy_status: ReviewStatus;
  generated_at: string;
  capabilities: (CoverageMetrics & {
    id: string;
    name: string;
    required_slices: (CoverageMetrics & { name: string })[];
    missing_accepted_slices: string[];
    unexecuted_slices: string[];
  })[];
  unmapped_trace_ids: string[];
  unmapped_task_ids: string[];
  stale_mapping_ids: string[];
  duplicate_groups: {
    kind: "trace" | "task";
    signature: string;
    entity_ids: string[];
  }[];
  source: unknown;
  scope: string;
}
export type FailureCause =
  | "agent_capability"
  | "missing_information"
  | "harness"
  | "environment"
  | "grader_false_pass"
  | "grader_false_fail"
  | "leakage"
  | "infrastructure"
  | "other";
export interface AttemptLabel {
  reviewer_kind?: "human" | "model";
  failure_cause?: FailureCause | null;
  task_id: string;
  trial: number;
  variant: "baseline" | "candidate";
  evidence_sha256: string;
  reviewer: string;
  status: GradeStatus;
  reason: string;
}
export interface AttemptAdjudication extends AttemptLabel {
  labels_sha256: string;
}
export interface CalibrationAttempt {
  task_id: string;
  trial: number;
  variant: "baseline" | "candidate";
  evidence_sha256: string;
  evidence: { task: TaskSpec; trial: Trial; provenance: unknown };
  labels: AttemptLabel[];
  adjudications: AttemptAdjudication[];
}
export interface CalibrationResolution {
  task_id: string;
  trial: number;
  variant: "baseline" | "candidate";
  evidence_sha256: string;
  labels_sha256: string;
  grader_status: GradeStatus;
  human_status: GradeStatus | null;
  resolution: "unlabeled" | "consensus" | "disagreement" | "adjudicated";
  reviewers: number;
  latest_labels: AttemptLabel[];
  model_labels?: AttemptLabel[];
  failure_cause?: FailureCause | null;
  cause_disagreement?: boolean;
  adjudication: AttemptAdjudication | null;
}
export interface CalibrationSummary {
  total: number;
  resolved: number;
  unlabeled: number;
  disagreements: number;
  adjudicated: number;
  confusion_matrix: Record<GradeStatus, Record<GradeStatus, number>>;
  false_pass: { count: number; denominator: number; rate: number | null };
  false_fail: { count: number; denominator: number; rate: number | null };
  invalid_disagreements: number;
  failure_causes?: Record<string, number>;
  cause_disagreements?: number;
  attempts: CalibrationResolution[];
  scope: string;
}
export interface Calibration {
  id: string;
  name: string;
  revision: number;
  created_at: string;
  snapshot: { experiment_id: string; split: string };
  attempts: CalibrationAttempt[];
}
export interface ImprovementCreate {
  name: string;
  hypothesis: string;
  expected_behavior: string;
  baseline_path: string;
  candidate_path: string;
  trace_ids: string[];
  task_ids: string[];
  parent_id?: string;
}
export interface Improvement {
  id: string;
  name: string;
  hypothesis: string;
  expected_behavior: string;
  baseline: unknown;
  candidate: unknown;
  patch: unknown;
  trace_ids: string[];
  task_ids: string[];
  experiments: { id: string; [key: string]: unknown }[];
  decisions: {
    experiment_id: string;
    decision: "keep" | "reject" | "inconclusive";
    reviewer: string;
    reason: string;
    at?: string;
  }[];
}
export interface Workflow {
  worlds: World[];
  improvements: Improvement[];
  calibrations: Calibration[];
  taxonomies: Taxonomy[];
  suites: { id: string; name?: string; tasks?: { split: string }[] }[];
}
export interface WorkflowExperiment {
  suite_id: string;
  baseline_path: string;
  candidate_path: string;
  improvement_id?: string;
  split: "optimization" | "validation" | "final";
  repeats: number;
  seed: number;
  judge?: "codex" | "claude";
  judge_model?: string;
}

export interface HarborExportConfig {
  template_directory: string;
  agent: string;
  model: string;
  environment_type: string;
  repetitions: number;
}
export interface HarborExport {
  id: string;
  kind: "harbor";
  task_id: string;
  bundle_directory: string;
  command: string[];
  validation: string;
  [key: string]: unknown;
}

export interface HarborAgentConfig {
  agent: string;
  model: string;
  agent_kwargs: Record<string, string | number | boolean>;
}
export interface HarborComparisonConfig {
  template_directory: string;
  baseline: HarborAgentConfig;
  candidate: HarborAgentConfig;
  environment_type: string;
  repetitions: number;
  reward_key: string;
  pass_threshold: number;
  timeout: number | null;
}
