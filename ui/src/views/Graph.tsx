import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  MiniMap,
  Position,
  ReactFlow,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../api";
import type { LineageGraph, LineageNode, Route } from "../contracts";
import { graphLayout, nodeRoute } from "../state";
import {
  Card,
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
      <div className="graph-canvas" aria-label="Evidence lineage graph">
        <ReactFlow
          nodes={nodes}
          edges={layout.edges}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          fitView
          minZoom={0.1}
          maxZoom={2}
          onNodeClick={(_, node) => setSelected(node.data)}
          onPaneClick={() => setSelected(null)}
        >
          <Background />
          <MiniMap
            pannable
            zoomable
            nodeColor={(node) => colors[(node.data as LineageNode).kind]}
          />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
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
}: {
  traceId?: string;
  navigate: (route: Route) => void;
}) {
  const [draft, setDraft] = useState(traceId);
  const [active, setActive] = useState(traceId);
  const request = useQuery({
    queryKey: ["graph", active],
    queryFn: ({ signal }) => api.graph(active, signal),
  });
  return (
    <>
      <Card title="Follow the evidence">
        <p>
          Explore how observed traces support findings, become tasks, and enter
          experiments.
        </p>
        <form className="row" onSubmit={submit(() => setActive(draft))}>
          <Field
            label="Focus on a trace ID (optional)"
            value={draft}
            onChange={setDraft}
            placeholder="All recorded lineage"
          />
          <button>Explore graph</button>
        </form>
      </Card>
      {request.data ? (
        <>
          <p className="scope-note">
            {request.data.scope} {request.data.shown_nodes} /{" "}
            {request.data.total_nodes} nodes shown.
            {request.data.truncated
              ? " The graph has been bounded; focus on a trace to inspect a smaller neighborhood."
              : ""}
          </p>
          {request.data.nodes.length ? (
            <GraphCanvas
              key={JSON.stringify(request.data)}
              graph={request.data}
              navigate={navigate}
            />
          ) : (
            <Card title="No recorded lineage">
              <p>
                Complete an investigation or create tasks. Traces without
                recorded relationships do not appear here.
              </p>
            </Card>
          )}
        </>
      ) : (
        <ResourceState error={request.error} />
      )}
    </>
  );
}
