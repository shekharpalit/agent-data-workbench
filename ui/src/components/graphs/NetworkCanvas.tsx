import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export function NetworkCanvas<T extends Record<string, unknown>>({
  label,
  nodes,
  edges,
  onSelect,
}: {
  label: string;
  nodes: Node<T>[];
  edges: Edge[];
  onSelect: (node: T | null) => void;
}) {
  return (
    <div className="graph-canvas" role="region" aria-label={label}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        fitView
        minZoom={0.05}
        maxZoom={2}
        onNodeClick={(_, node) => onSelect(node.data)}
        onPaneClick={() => onSelect(null)}
      >
        <Background />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
