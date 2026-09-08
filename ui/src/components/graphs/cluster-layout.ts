import type { Cluster } from "../../contracts";

export type ClusterNode = {
  label: string;
  kind: "cluster" | "trace";
  trace_id?: string;
};

export function clusterLayout(cluster: Cluster) {
  const root = `cluster:${cluster.id}`;
  const columns = Math.max(1, Math.ceil(Math.sqrt(cluster.trace_ids.length)));
  const nodes = [
    {
      id: root,
      data: {
        kind: "cluster" as const,
        label: `${cluster.count} traces · ${cluster.label}`,
      },
      position: { x: ((columns - 1) * 280) / 2, y: 0 },
    },
    ...cluster.trace_ids.map((trace_id, index) => ({
      id: `trace:${trace_id}`,
      data: { kind: "trace" as const, label: trace_id, trace_id },
      position: {
        x: (index % columns) * 280,
        y: 180 + Math.floor(index / columns) * 120,
      },
    })),
  ];
  return {
    nodes,
    edges: cluster.trace_ids.map((trace_id) => ({
      id: `${root}:trace:${trace_id}`,
      source: root,
      target: `trace:${trace_id}`,
      label: "member",
    })),
  };
}
