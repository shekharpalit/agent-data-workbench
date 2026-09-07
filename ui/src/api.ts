import type {
  ArtifactMap,
  Audit,
  Backend,
  ClusterRequest,
  ClusterResult,
  Distribution,
  Job,
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
    backend: Backend;
    model: string;
    steps: number;
  }) => this.request<{ job_id: string }>("/api/investigate", request);
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
  editTask = (id: string, spec: TaskSpec, note: string) =>
    this.request<Task>("/api/task/edit", { id, spec, note });
}

export const api = new ApiClient(
  () => sessionStorage.getItem("agent-data-workbench-token") || "",
);
