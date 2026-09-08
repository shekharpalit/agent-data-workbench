import { useMemo, useState } from "react";
import { Position, type Node } from "@xyflow/react";
import type { Cluster, Route } from "../../contracts";
import { clusterLayout, type ClusterNode } from "./cluster-layout";
import { NetworkCanvas } from "./NetworkCanvas";
import { Card } from "../shared";

export default function ClusterGraph({
  clusters,
  navigate,
  onMembers,
}: {
  clusters: Cluster[];
  navigate: (route: Route) => void;
  onMembers: (ids: string[]) => void;
}) {
  const [active, setActive] = useState(clusters[0]?.id || "");
  const [selected, setSelected] = useState<ClusterNode | null>(null);
  const cluster = clusters.find((item) => item.id === active) || clusters[0];
  const layout = useMemo(
    () => (cluster ? clusterLayout(cluster) : null),
    [cluster],
  );
  if (!cluster || !layout) return null;
  const nodes: Node<ClusterNode>[] = layout.nodes.map((node) => ({
    ...node,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    selected:
      selected?.trace_id !== undefined &&
      node.data.kind === "trace" &&
      selected.trace_id === node.data.trace_id,
    style: {
      background: node.data.kind === "cluster" ? "#f7e5be" : "#d9eadf",
      width: 220,
      padding: 16,
      borderRadius: 10,
      border: "1px solid #b4c2b9",
    },
  }));
  return (
    <Card title="Cluster map">
      <label className="field">
        <span>Cluster to visualize</span>
        <select
          value={cluster.id}
          onChange={(event) => {
            setActive(event.target.value);
            setSelected(null);
          }}
        >
          {clusters.map((item, index) => (
            <option key={item.id} value={item.id}>
              Group {index + 1} · {item.count} traces · {item.label}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">
        Edges show membership in a lexical group. Select a trace to inspect its
        evidence; use the selector to explore another group.
      </p>
      <NetworkCanvas
        key={cluster.id}
        label="Trace cluster graph"
        nodes={nodes}
        edges={layout.edges}
        onSelect={setSelected}
      />
      <div className="row">
        <button
          className="secondary"
          onClick={() => onMembers(cluster.trace_ids)}
        >
          Inspect all {cluster.count} members →
        </button>
        {selected?.trace_id && (
          <button
            onClick={() => navigate({ view: "traces", id: selected.trace_id })}
          >
            Open selected trace →
          </button>
        )}
      </div>
      {selected?.trace_id && <p className="mono">{selected.trace_id}</p>}
    </Card>
  );
}
