import type {
  FieldFilter,
  LineageGraph,
  LineageNode,
  Route,
  SearchQuery,
} from "./contracts";

export const initialSearch: SearchQuery = {
  text: "",
  stratum: "",
  filters: [],
  sort: "trace_id",
  direction: "asc",
  limit: 20,
  offset: 0,
  trace_ids: null,
};
export type SearchAction =
  | { type: "apply"; query: SearchQuery }
  | { type: "page"; offset: number }
  | { type: "cluster"; ids: string[] }
  | { type: "reset" };
export function searchReducer(
  state: SearchQuery,
  action: SearchAction,
): SearchQuery {
  switch (action.type) {
    case "apply":
      return { ...action.query, offset: 0 };
    case "page":
      return { ...state, offset: Math.max(0, action.offset) };
    case "cluster":
      return { ...state, trace_ids: [...action.ids], offset: 0 };
    case "reset":
      return { ...initialSearch, filters: [] };
  }
}
export function filterValue(
  operator: FieldFilter["operator"],
  value: string,
): string {
  if (operator === "exists" || operator === "missing") return "null";
  if (operator === "contains") return JSON.stringify(value);
  try {
    const parsed: unknown = JSON.parse(value);
    if (
      (operator === "gte" || operator === "lte") &&
      (typeof parsed !== "number" || !Number.isFinite(parsed))
    )
      throw new Error();
    return JSON.stringify(parsed);
  } catch {
    if (operator === "gte" || operator === "lte")
      throw new Error("Numeric ranges require a number.");
    return JSON.stringify(value);
  }
}
export function nodeRoute(node: LineageNode): Route | null {
  if (node.kind === "trace" && node.trace_id)
    return { view: "traces", id: node.trace_id };
  if (!node.artifact_id) return null;
  return {
    view:
      node.kind === "finding"
        ? "investigations"
        : node.kind === "task"
          ? "tasks"
          : "experiments",
    id: node.artifact_id,
  };
}
export function graphLayout(graph: LineageGraph) {
  const columns = { trace: 0, finding: 1, task: 2, experiment: 3 };
  const counts = { trace: 0, finding: 0, task: 0, experiment: 0 };
  const onlyTraces = graph.nodes.every((node) => node.kind === "trace");
  const gridColumns = Math.max(1, Math.ceil(Math.sqrt(graph.nodes.length)));
  const nodes = graph.nodes.map((node, index) => ({
    id: node.id,
    data: node,
    position: onlyTraces
      ? {
          x: (index % gridColumns) * 330,
          y: Math.floor(index / gridColumns) * 140,
        }
      : { x: columns[node.kind] * 330, y: counts[node.kind]++ * 120 },
  }));
  const ids = new Set(nodes.map((node) => node.id));
  return {
    nodes,
    edges: graph.edges.filter(
      (edge) => ids.has(edge.source) && ids.has(edge.target),
    ),
  };
}
