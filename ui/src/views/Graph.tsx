import { DatasetView } from "./Dataset";
import type { SearchQuery } from "../contracts";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Position, type Node } from "@xyflow/react";
import { NetworkCanvas } from "../components/graphs/NetworkCanvas";
import { api } from "../api";
import type { LineageGraph, LineageNode, Route } from "../contracts";
import { graphLayout, nodeRoute } from "../state";
import {
  Card,
  Details,
  Field,
  JsonView,
  ResourceState,
  submit,
} from "../components/shared";

const colors = {
  trace: "#d9eadf",
  finding: "#f7e5be",
  task: "#dce5f4",
  experiment: "#e7dcf0",
};
function GraphCanvas({
  graph,
  navigate,
}: {
  graph: LineageGraph;
  navigate: (route: Route) => void;
}) {
  const [selected, setSelected] = useState<LineageNode | null>(null);
  const layout = useMemo(() => graphLayout(graph), [graph]);
  const nodes: Node<LineageNode>[] = useMemo(
    () =>
      layout.nodes.map((node) => ({
        ...node,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          background: colors[node.data.kind],
          width: 240,
          borderRadius: 10,
          border: "1px solid #b4c2b9",
          padding: 18,
        },
        selected: selected?.id === node.id,
      })),
    [layout, selected],
  );
  const route = selected ? nodeRoute(selected) : null;
  return (
    <>
      <div className="graph-legend">
        {Object.entries(colors).map(([kind, color]) => (
          <span key={kind}>
            <i style={{ background: color }} />
            {kind}
          </span>
        ))}
      </div>
      <NetworkCanvas
        label="Evidence lineage graph"
        nodes={nodes}
        edges={layout.edges}
        onSelect={setSelected}
      />
      <Card title={selected?.label || "Inspect a connection"}>
        {selected ? (
          <>
            <p>
              {selected.kind} · {selected.status || "recorded evidence"}
            </p>
            {route && (
              <button onClick={() => navigate(route)}>
                Open source artifact →
              </button>
            )}
            {graph.edges
              .filter(
                (edge) =>
                  edge.source === selected.id || edge.target === selected.id,
              )
              .map((edge) => (
                <p key={edge.id}>
                  <strong>
                    {graph.nodes.find((node) => node.id === edge.source)?.label}
                  </strong>{" "}
                  {edge.label}{" "}
                  <strong>
                    {graph.nodes.find((node) => node.id === edge.target)?.label}
                  </strong>
                  .
                </p>
              ))}
            <JsonView value={selected} />
          </>
        ) : (
          <p className="muted">
            Pan or zoom the graph. Select a node to open its trace,
            investigation, task or experiment.
          </p>
        )}
      </Card>
    </>
  );
}
export default function GraphView({
  traceId = "",
  navigate,
  query,
  onMembers,
}: {
  traceId?: string;
  query: SearchQuery;
  onMembers: (ids: string[]) => void;
  navigate: (route: Route) => void;
}) {
  const [mode, setMode] = useState(traceId ? "evidence" : "dataset");
  const [draft, setDraft] = useState(traceId);
  const [active, setActive] = useState(traceId);
  const request = useQuery({
    queryKey: ["graph", active],
    enabled: mode === "evidence",
    queryFn: ({ signal }) => api.graph(active, signal),
  });
  return (
    <>
      <div className="view-tabs">
        <button
          className={mode === "dataset" ? "" : "secondary"}
          onClick={() => setMode("dataset")}
        >
          Dataset overview
        </button>
        <button
          className={mode === "evidence" ? "" : "secondary"}
          onClick={() => setMode("evidence")}
        >
          Evidence lineage
        </button>
      </div>
      {mode === "dataset" ? (
        <DatasetView query={query} onMembers={onMembers} navigate={navigate} />
      ) : (
        <>
          <Card title="Follow the evidence">
            <p>
              Explore imported traces and their saved links to findings, tasks
              and experiments. Select a trace to inspect its original events.
            </p>
            <form className="row" onSubmit={submit(() => setActive(draft))}>
              <Field
                label="Focus on a trace ID (optional)"
                value={draft}
                onChange={setDraft}
                placeholder="All imported traces and recorded lineage"
              />
              <button>Explore graph</button>
            </form>
          </Card>
          {request.data ? (
            <>
              <p className="scope-note">
                {
                  request.data.nodes.filter((node) =>
                    request.data.edges.some(
                      (edge) =>
                        edge.source === node.id || edge.target === node.id,
                    ),
                  ).length
                }{" "}
                linked nodes shown from {request.data.total_nodes} known
                records. Unlinked records remain available in Trace explorer.{" "}
                {request.data.scope}
                {request.data.truncated
                  ? " An explicit maximum limited this response; omit it to retrieve every node."
                  : ""}
              </p>
              <Details title="All source records and saved relationships">
                <JsonView value={request.data} />
              </Details>
              {request.data.nodes.length > 0 &&
                request.data.edges.length === 0 && (
                  <Card title="Imported traces are ready to explore">
                    <p>
                      No evidence relationships have been saved yet. Start an
                      investigation to connect exact trace evidence to findings
                      and reviewed evaluation tasks.
                    </p>
                    <button
                      onClick={() => navigate({ view: "investigations" })}
                    >
                      Start an investigation →
                    </button>
                  </Card>
                )}
              {request.data.edges.length ? (
                <GraphCanvas
                  key={JSON.stringify(request.data)}
                  graph={{
                    ...request.data,
                    nodes: request.data.nodes.filter((node) =>
                      request.data.edges.some(
                        (edge) =>
                          edge.source === node.id || edge.target === node.id,
                      ),
                    ),
                  }}
                  navigate={navigate}
                />
              ) : request.data.nodes.length === 0 ? (
                <Card
                  title={
                    active
                      ? "No matching trace or evidence"
                      : "No traces imported"
                  }
                >
                  <p>
                    {active
                      ? "Check the trace ID or clear it to show all imported evidence."
                      : "Import JSON or JSONL traces to start exploring the graph."}
                  </p>
                </Card>
              ) : null}
            </>
          ) : (
            <ResourceState error={request.error} />
          )}
        </>
      )}
    </>
  );
}
