import type {
  DatasetImport,
  DatasetSource,
  ImportReceipt,
  DatasetProfile,
} from "./data-contracts";
import type {
  HarborComparisonConfig,
  HarborExport,
  HarborExportConfig,
  AttemptAdjudication,
  AttemptLabel,
  BehavioralCoverage,
  Calibration,
  CalibrationSummary,
  CoverageMapping,
  Improvement,
  ImprovementCreate,
  Taxonomy,
  TaxonomySpec,
  Workflow,
  WorkflowExperiment,
  World,
  WorldSpec,
} from "./workflow-contracts";
import type {
  ArtifactMap,
  Coverage,
  Investigation,
  RecordOutcome,
  ResearchArtifact,
  ResearchChart,
  ResearchResult,
  ResearchSearch,
  ResearchSearchPage,
  ResearchTracePage,
  Audit,
  Backend,
  ClusterRequest,
  ClusterResult,
  Distribution,
  Job,
  Journal,
  OutcomePage,
  Knowledge,
  LineageGraph,
  Overview,
  ReviewStatus,
  SearchQuery,
  SearchResult,
  Task,
  TaskSpec,
  Trace,
} from "./contracts";

export function sessionToken(hash: string, previous: string): string {
  return new URLSearchParams(hash.replace(/^#/, "")).get("token") || previous;
}

export class ApiClient {
  constructor(
    private readonly token: () => string,
    private readonly transport: typeof fetch = (...args) => fetch(...args),
  ) {}

  private async request<T>(
    path: string,
    payload?: unknown,
    signal?: AbortSignal,
  ): Promise<T> {
    const response = await this.transport(path, {
      method: payload === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${this.token()}`,
        ...(payload === undefined
          ? {}
          : { "Content-Type": "application/json" }),
      },
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
      ...(signal ? { signal } : {}),
    });
    const data: unknown = await response.json();
    if (!response.ok) {
      const message =
        typeof data === "object" &&
        data !== null &&
        "error" in data &&
        typeof data.error === "string"
          ? data.error
          : "Request failed";
      throw new Error(message);
    }
    return data as T;
  }

  runtime = (signal?: AbortSignal) =>
    this.request<{
      environment: string;
      tools: {
        name: string;
        installed: boolean;
        executable: string | null;
        version: string | null;
        authentication: string;
        ready: boolean;
      }[];
    }>("/api/runtime", undefined, signal);
  compareHarbor = (task_id: string, config: HarborComparisonConfig) =>
    this.request<{ job_id: string }>("/api/workflow/harbor/compare", {
      task_id,
      config,
    });
  imports = (signal?: AbortSignal) =>
    this.request<ImportReceipt[]>("/api/imports", undefined, signal);
  inspectDataset = (config: DatasetImport) =>
    this.request<{ source: DatasetSource; config: DatasetImport }>(
      "/api/imports/huggingface/inspect",
      config,
    );
  importDataset = (config: DatasetImport) =>
    this.request<{ job_id: string }>("/api/imports/huggingface", config);
  datasetProfile = (
    query: SearchQuery,
    pointer: string,
    signal?: AbortSignal,
  ) =>
    this.request<DatasetProfile>(
      "/api/dataset-profile",
      { query, pointer },
      signal,
    );
  overview = (signal?: AbortSignal) =>
    this.request<Overview>("/api/overview", undefined, signal);
  search = (query: SearchQuery, signal?: AbortSignal) =>
    this.request<SearchResult>("/api/search", query, signal);
  distribution = (query: SearchQuery, pointer: string, signal?: AbortSignal) =>
    this.request<Distribution>("/api/distribution", { query, pointer }, signal);
  clusters = (request: ClusterRequest, signal?: AbortSignal) =>
    this.request<ClusterResult>("/api/clusters", request, signal);
  graph = (traceId: string, signal?: AbortSignal) =>
    this.request<LineageGraph>(
      `/api/graph?trace_id=${encodeURIComponent(traceId)}`,
      undefined,
      signal,
    );
  trace = (id: string, signal?: AbortSignal) =>
    this.request<Trace>(
      `/api/trace?id=${encodeURIComponent(id)}`,
      undefined,
      signal,
    );
  artifacts = <K extends keyof ArtifactMap>(kind: K, signal?: AbortSignal) =>
    this.request<ArtifactMap[K][]>(
      `/api/artifacts?kind=${kind}`,
      undefined,
      signal,
    );
  artifact = <K extends keyof ArtifactMap>(
    kind: K,
    id: string,
    signal?: AbortSignal,
  ) =>
    this.request<ArtifactMap[K]>(
      `/api/artifact?kind=${kind}&id=${encodeURIComponent(id)}`,
      undefined,
      signal,
    );
  jobs = (signal?: AbortSignal) =>
    this.request<Job[]>("/api/jobs", undefined, signal);
  investigate = (request: {
    question?: string;
    resume?: string;
    backend?: Backend;
    model?: string;
    mode?: "research" | "complete";
    exclude_final?: boolean;
  }) => this.request<{ job_id: string }>("/api/investigate", request);
  createResearch = (request: {
    question: string;
    mode: "research" | "complete";
    exclude_final: boolean;
  }) => this.request<Investigation>("/api/investigation/create", request);
  searchResearch = (
    id: string,
    query: ResearchSearch,
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams({
      id,
      text: query.text,
      stratum: query.stratum,
      pending_only: String(query.pending_only),
    });
    if (query.after !== null) params.set("after", query.after);
    return this.request<ResearchSearchPage>(
      `/api/investigation/search?${params}`,
      undefined,
      signal,
    );
  };
  researchTrace = (
    id: string,
    traceId: string,
    pointer: string,
    offset: number,
    signal?: AbortSignal,
  ) =>
    this.request<ResearchTracePage>(
      `/api/investigation/trace?${new URLSearchParams({ id, trace_id: traceId, pointer, offset: String(offset) })}`,
      undefined,
      signal,
    );
  researchCheckpoint = (id: string, note: string) =>
    this.request<Coverage>("/api/investigation/checkpoint", { id, note });
  recordResearch = (id: string, outcomes: RecordOutcome[]) =>
    this.request<Coverage>("/api/investigation/record", { id, outcomes });
  publishResearch = (id: string, result: ResearchResult, complete: boolean) =>
    this.request<{ id: string; status: string; coverage: Coverage }>(
      "/api/investigation/publish",
      { id, result, complete },
    );
  createResearchChart = (id: string, chart: ResearchChart) =>
    this.request<ResearchArtifact>("/api/investigation/chart", { id, chart });
  pauseResearch = (id: string) =>
    this.request("/api/investigation/pause", { id });
  researchJournal = (id: string, offset: number, signal?: AbortSignal) =>
    this.request<Journal>(
      `/api/investigation/journal?id=${encodeURIComponent(id)}&offset=${offset}`,
      undefined,
      signal,
    );
  researchOutcomes = (id: string, after: string | null, signal?: AbortSignal) =>
    this.request<OutcomePage>(
      `/api/investigation/outcomes?id=${encodeURIComponent(id)}${after === null ? "" : `&after=${encodeURIComponent(after)}`}`,
      undefined,
      signal,
    );
  async researchFile(id: string, artifact: string): Promise<Blob> {
    const response = await this.transport(
      `/api/investigation/file?id=${encodeURIComponent(id)}&artifact=${encodeURIComponent(artifact)}`,
      {
        headers: { Authorization: `Bearer ${this.token()}` },
      },
    );
    if (!response.ok)
      throw new Error("Could not download this research artifact");
    return response.blob();
  }
  designTasks = (investigation: string, backend: Backend, model: string) =>
    this.request<{ job_id: string }>("/api/task/design", {
      investigation,
      backend,
      model,
    });
  addKnowledge = (title: string, source: string, content: string) =>
    this.request<Knowledge>("/api/knowledge/add", { title, source, content });
  reviewKnowledge = (id: string, status: ReviewStatus, note: string) =>
    this.request<Knowledge>("/api/knowledge/review", { id, status, note });
  auditTask = (id: string) => this.request<Audit>("/api/task/audit", { id });
  reviewTask = (id: string, status: ReviewStatus, note: string) =>
    this.request<Task>("/api/task/review", { id, status, note });
  exportHarbor = (task_id: string, config: HarborExportConfig) =>
    this.request<HarborExport>("/api/workflow/harbor/export", {
      task_id,
      config,
    });
  workflow = (signal?: AbortSignal) =>
    this.request<Workflow>("/api/workflow", undefined, signal);
  createWorld = (spec: WorldSpec, previous_id?: string) =>
    this.request<World>("/api/workflow/world", {
      spec,
      ...(previous_id ? { previous_id } : {}),
    });
  reviewWorld = (
    id: string,
    status: ReviewStatus,
    note: string,
    reviewer: string,
  ) =>
    this.request<World>("/api/workflow/world/review", {
      id,
      status,
      note,
      reviewer,
    });
  createTaxonomy = (spec: TaxonomySpec, previous_id?: string) =>
    this.request<Taxonomy>("/api/workflow/taxonomy", {
      spec,
      ...(previous_id ? { previous_id } : {}),
    });
  reviewTaxonomy = (
    id: string,
    status: ReviewStatus,
    note: string,
    reviewer: string,
  ) =>
    this.request<Taxonomy>("/api/workflow/taxonomy/review", {
      id,
      status,
      note,
      reviewer,
    });
  behavioralCoverage = (id: string, signal?: AbortSignal) =>
    this.request<BehavioralCoverage>(
      `/api/workflow/coverage/${encodeURIComponent(id)}`,
      undefined,
      signal,
    );
  mapCoverage = (taxonomy_id: string, mapping: CoverageMapping) =>
    this.request<unknown>("/api/workflow/coverage/map", {
      taxonomy_id,
      mapping,
    });
  createCalibration = (experiment_id: string, name: string) =>
    this.request<Calibration>("/api/workflow/calibration", {
      experiment_id,
      name,
    });
  calibration = (id: string, signal?: AbortSignal) =>
    this.request<{ calibration: Calibration; summary: CalibrationSummary }>(
      `/api/workflow/calibration/${encodeURIComponent(id)}`,
      undefined,
      signal,
    );
  labelAttempt = (id: string, label: AttemptLabel) =>
    this.request<Calibration>("/api/workflow/calibration/label", { id, label });
  adjudicateAttempt = (id: string, decision: AttemptAdjudication) =>
    this.request<Calibration>("/api/workflow/calibration/adjudicate", {
      id,
      decision,
    });
  createImprovement = (request: ImprovementCreate) =>
    this.request<Improvement>("/api/workflow/improvement", request);
  decideImprovement = (request: {
    id: string;
    experiment_id: string;
    decision: "keep" | "reject" | "inconclusive";
    reviewer: string;
    reason: string;
  }) =>
    this.request<Improvement>("/api/workflow/improvement/decision", request);
  runWorkflowExperiment = (request: WorkflowExperiment) =>
    this.request<{ job_id: string }>("/api/workflow/experiment", request);
  editTask = (id: string, spec: TaskSpec, note: string) =>
    this.request<Task>("/api/task/edit", { id, spec, note });
}

export const api = new ApiClient(
  () => sessionStorage.getItem("agent-data-workbench-token") || "",
);
