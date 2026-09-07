export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export type View =
  | "overview"
  | "traces"
  | "clusters"
  | "graph"
  | "investigations"
  | "knowledge"
  | "tasks"
  | "experiments";
export type Route = { view: View; id?: string };
export type ReviewStatus = "draft" | "accepted" | "rejected";
export type GradeStatus = "pass" | "fail" | "invalid";
export type Backend = "codex" | "claude";
export interface FieldFilter {
  pointer: string;
  operator: "equals" | "contains" | "gte" | "lte" | "exists" | "missing";
  value_json: string;
}
export interface SearchQuery {
  text: string;
  stratum: string;
  filters: FieldFilter[];
  sort: string;
  direction: "asc" | "desc";
  limit: number;
  offset: number;
  trace_ids: string[] | null;
}
export interface Trace {
  trace_id: string;
  data: Record<string, Json>;
  stratum?: string;
  group_id?: string;
}
export interface SearchResult {
  query: SearchQuery;
  eligible: number;
  selected: number;
  ids: string[];
  records: Trace[];
  strata: Record<string, number>;
  source_sha256: string;
}
export interface Distribution {
  pointer: string;
  eligible: number;
  missing_or_non_scalar: number;
  counts: { value: Json; count: number }[];
  distinct: number;
  numeric_count: number;
  mean: number | null;
  minimum: number | null;
  maximum: number | null;
}
export interface ClusterRequest {
  query: SearchQuery;
  pointer: string;
  threshold: number;
  limit: number;
}
export interface Cluster {
  id: string;
  trace_ids: string[];
  count: number;
  terms: string[];
  label: string;
}
export interface ClusterResult {
  method: string;
  pointer: string;
  threshold: number;
  eligible: number;
  sampled: number;
  clustered: number;
  omitted_ids: string[];
  text_limit_chars: number;
  text_truncated_ids: string[];
  truncated: boolean;
  source_sha256: string;
  clusters: Cluster[];
  scope: string;
}
export type LineageNode = {
  id: string;
  kind: "trace" | "finding" | "task" | "experiment";
  label: string;
  artifact_id?: string;
  trace_id?: string;
  finding_id?: string;
  status?: string;
};
export interface LineageEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}
export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
  total_nodes: number;
  shown_nodes: number;
  truncated: boolean;
  trace_id: string;
  scope: string;
}
export interface Evidence {
  trace_id: string;
  pointer: string;
  quote: string;
}
export interface Finding {
  id: string;
  title: string;
  category: string;
  confidence: string;
  explanation: string;
  recommendation: string;
  evidence: Evidence[];
}
export interface Proposal {
  id: string;
  title: string;
  kind: string;
  finding_ids: string[];
  hypothesis: string;
  expected_effect: string;
  evaluation_plan: string;
  edits: { path: string; before: string; after: string }[];
}
export interface Coverage {
  total: number;
  retrieved: number;
  completed: number;
  failed: number;
  pending: number;
}
export interface Journal {
  items: {
    id: string;
    at: string;
    kind: string;
    note: string;
    details: Json;
  }[];
  total: number;
  next_offset: number | null;
}
export interface OutcomePage {
  records: {
    trace_id: string;
    status: string;
    output: Json;
    error: string | null;
    method: string | null;
  }[];
  next_cursor: string | null;
}
export interface ResearchArtifact {
  id: string;
  title: string;
  kind: string;
  filename: string;
  bytes: number;
  chart: {
    title: string;
    description: string;
    values: { label: string; value: number }[];
  } | null;
}
export interface Investigation {
  id: string;
  created_at: string;
  question: string;
  status: string;
  error: string | null;
  source: { total: number };
  protocol_version?: string;
  mode?: "research" | "complete";
  active: boolean;
  session?: {
    backend: Backend;
    model: string | null;
    id: string | null;
  } | null;
  attempts?: {
    id: string;
    status: string;
    started_at: string;
    finished_at?: string;
  }[];
  coverage: Coverage;
  published_coverage?: Coverage;
  journal: Journal;
  attachments?: ResearchArtifact[];
  result: ResearchResult | null;
}
export interface Knowledge {
  id: string;
  title: string;
  content: string;
  source: string;
  status: ReviewStatus;
  revision: number;
  created_at: string;
}
export interface Criterion {
  id: string;
  description: string;
  source: "output" | "artifact";
  artifact: string;
  kind: "assertion" | "semantic";
  assertion: null | { pointer: string; operator: string; expected: string };
  rubric: string;
}
export interface TaskSpec {
  id: string;
  title: string;
  purpose: string;
  behavior: string;
  finding_ids: string[];
  trace_ids: string[];
  fidelity: "output" | "next_action" | "environment";
  input_json: string;
  context_sha256: string;
  assumptions: string[];
  missing_context: string[];
  criteria: Criterion[];
  verifier_examples: {
    name: string;
    kind: string;
    output_json: string;
    artifacts_json: string;
    expected: GradeStatus;
  }[];
}
export interface Audit {
  at: string;
  passed: boolean;
  missing_kinds: string[];
  results: {
    name: string;
    kind: string;
    expected: GradeStatus;
    actual: GradeStatus;
    matched: boolean;
    checks: Json[];
  }[];
  scope: string;
}
export interface Task {
  id: string;
  spec: TaskSpec;
  origin: string;
  created_at: string;
  review: { status: ReviewStatus; note: string };
  audit: Audit | null;
  revisions?: { at: string; note: string; spec: TaskSpec }[];
}
export interface VariantSummary {
  passed: number;
  failed: number;
  invalid: number;
  total: number;
  valid: number;
  pass_rate: number | null;
  recorded_cost_usd: number | null;
  cost_coverage: number;
  mean_latency_seconds: number | null;
}
export interface ExperimentSummary {
  baseline?: VariantSummary;
  candidate?: VariantSummary;
  improved: { task_id: string; trial: number }[];
  regressed: { task_id: string; trial: number }[];
  invalid_pairs: { task_id: string; trial: number }[];
  task_mean_delta: number | null;
  task_bootstrap_95_interval: [number, number] | null;
  independent_groups: number;
  uncertainty_note: string;
}
export interface Trial {
  task_id: string;
  trial: number;
  variant: "baseline" | "candidate";
  grade: { status: GradeStatus; checks: Json[] };
  execution: {
    output: Record<string, Json>;
    status: string;
    latency_seconds: number;
    cost_usd: number | null;
  };
  artifacts: Record<string, Json>;
}
export interface Experiment {
  id: string;
  created_at: string;
  suite_id: string;
  split: string;
  repeats: number;
  status: string;
  conclusion: string;
  summary: ExperimentSummary;
  trials: Trial[];
  baseline: Json;
  candidate: Json;
  judge: Json;
  context_sha256: string;
  suite_sha256: string;
  host: Json;
  previously_investigated_tasks?: string[];
}
export interface ArtifactMap {
  investigations: Investigation;
  knowledge: Knowledge;
  tasks: Task;
  experiments: Experiment;
}
export interface Overview {
  project: { name: string; objective: string; success_criteria: string[] };
  inventory: { total: number; strata: Record<string, number> };
  task_counts: Record<ReviewStatus, number>;
  experiments: Pick<
    Experiment,
    "id" | "created_at" | "split" | "status" | "summary" | "conclusion"
  >[];
}
export interface Job {
  id: string;
  name: string;
  status: "running" | "complete" | "error";
  error: string | null;
}

export interface ResearchResult {
  analysis: {
    summary: string;
    findings: Finding[];
    cases: {
      id: string;
      title: string;
      finding_ids: string[];
      trace_ids: string[];
      input: string;
      required_context: string[];
      assertions: { pointer: string; operator: string; expected: string }[];
    }[];
    limitations: string[];
  };
  signals: {
    finding_id: string;
    kind: string;
    impact: string;
    impact_reason: string;
    evidence: Evidence[];
  }[];
  proposals: Proposal[];
  open_questions: string[];
}
export interface ResearchChart {
  title: string;
  description: string;
  values: { label: string; value: number }[];
}
export interface ResearchSearch {
  text: string;
  stratum: string;
  after: string | null;
  pending_only: boolean;
}
export interface ResearchSearchPage {
  records: {
    trace_id: string;
    stratum: string;
    group_id: string;
    preview: string;
    total_chars: number;
    truncated: boolean;
    status: string;
  }[];
  next_cursor: string | null;
  coverage: Coverage;
}
export interface ResearchTracePage {
  trace_id: string;
  pointer: string;
  content: string;
  offset: number;
  total_chars: number;
  next_offset: number | null;
}
export interface RecordOutcome {
  trace_id: string;
  output: Record<string, Json> | null;
  error: string | null;
  method: string;
}
