import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import type { ClusterResult, LineageGraph } from "../src/contracts";
import { initialSearch, graphLayout } from "../src/state";
import { ClustersView } from "../src/views/Clusters";
import GraphView from "../src/views/Graph";
import { clusterLayout } from "../src/components/graphs/cluster-layout";

vi.mock("../src/components/graphs/NetworkCanvas", () => ({
  NetworkCanvas: ({
    label,
    nodes,
    onSelect,
  }: {
    label: string;
    nodes: { id: string; data: { label: string } }[];
    onSelect: (node: { label: string }) => void;
  }) => (
    <section aria-label={label}>
      {nodes.map((node) => (
        <button key={node.id} onClick={() => onSelect(node.data)}>
          {node.data.label}
        </button>
      ))}
    </section>
  ),
}));

const groups = [
  {
    id: "first",
    count: 2,
    trace_ids: ["scan-a", "scan-b"],
    terms: ["schema"],
    label: "schema",
  },
  {
    id: "second",
    count: 1,
    trace_ids: ["scan-c"],
    terms: ["timeout"],
    label: "timeout",
  },
];
const result: ClusterResult = {
  method: "TF-IDF cosine connected components",
  pointer: "",
  threshold: 0.55,
  eligible: 3,
  sampled: 3,
  clustered: 3,
  omitted_ids: [],
  text_limit_chars: null,
  text_truncated_ids: [],
  truncated: false,
  source_sha256: "fixture",
  clusters: groups,
  scope: "All matching traces, complete text.",
};
function renderQuery(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

describe("trace exploration", () => {
  it("Given event traces, When opening Clusters, Then automatically reads whole records and opens mapped members", async () => {
    // Given
    const request = vi.spyOn(api, "clusters").mockResolvedValue(result);
    const navigate = vi.fn();
    const onMembers = vi.fn();
    const user = userEvent.setup();
    renderQuery(
      <ClustersView
        query={initialSearch}
        navigate={navigate}
        onMembers={onMembers}
      />,
    );
    // When
    await user.click(await screen.findByRole("button", { name: "scan-a" }));
    await user.click(
      screen.getByRole("button", { name: "Open selected trace →" }),
    );
    await user.selectOptions(
      screen.getByLabelText("Cluster to visualize"),
      "second",
    );
    await user.click(
      screen.getByRole("button", { name: "Inspect all 1 members →" }),
    );
    // Then
    expect({
      request: request.mock.calls[0]?.[0],
      navigation: navigate.mock.calls,
      members: onMembers.mock.calls,
    }).toStrictEqual({
      request: {
        query: initialSearch,
        pointer: "",
        threshold: 0.55,
        limit: null,
      },
      navigation: [[{ view: "traces", id: "scan-a" }]],
      members: [[["scan-c"]]],
    });
  });

  it("Given a missing selected field, When grouping, Then explains how to recover and respects an explicit maximum", async () => {
    // Given
    const request = vi
      .spyOn(api, "clusters")
      .mockResolvedValueOnce(result)
      .mockResolvedValue({
        ...result,
        pointer: "/input",
        clustered: 0,
        clusters: [],
        omitted_ids: ["scan-a", "scan-b", "scan-c"],
      });
    const user = userEvent.setup();
    renderQuery(
      <ClustersView
        query={initialSearch}
        navigate={vi.fn()}
        onMembers={vi.fn()}
      />,
    );
    await screen.findByRole("heading", { name: "2 groups from 3 traces" });
    // When
    await user.type(
      screen.getByLabelText("Text field (JSON pointer; empty uses the record)"),
      "/input",
    );
    await user.type(screen.getByLabelText("Maximum traces (optional)"), "300");
    await user.click(screen.getByRole("button", { name: "Group traces" }));
    await screen.findByRole("heading", {
      name: "No usable text in the selected field",
    });
    // Then
    expect({
      request: request.mock.calls.at(-1)?.[0],
      recovery: screen.getByText(
        "Clear the text field to use complete records, or choose a JSON pointer present in these traces.",
      ).textContent,
    }).toStrictEqual({
      request: {
        query: initialSearch,
        pointer: "/input",
        threshold: 0.55,
        limit: 300,
      },
      recovery:
        "Clear the text field to use complete records, or choose a JSON pointer present in these traces.",
    });
  });

  it("Given an imported trace with no findings, When opening its graph node, Then opens the original trace", async () => {
    // Given
    vi.spyOn(api, "graph").mockResolvedValue({
      nodes: [
        {
          id: "trace:scan-a",
          kind: "trace",
          label: "scans/run.jsonl",
          trace_id: "scan-a",
        },
      ],
      edges: [],
      total_nodes: 1,
      shown_nodes: 1,
      truncated: false,
      trace_id: "",
      scope: "Imported evidence.",
    });
    const navigate = vi.fn();
    const user = userEvent.setup();
    renderQuery(<GraphView navigate={navigate} />);
    // When
    await user.click(
      await screen.findByRole("button", { name: "scans/run.jsonl" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Open source artifact →" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Explore trace clusters →" }),
    );
    // Then
    expect(navigate.mock.calls).toStrictEqual([
      [{ view: "traces", id: "scan-a" }],
      [{ view: "clusters" }],
    ]);
  });

  it("Given raw traces, When arranging the graph, Then uses a readable grid without inventing edges", () => {
    // Given
    const nodes: LineageGraph["nodes"] = ["a", "b", "c", "d"].map((id) => ({
      id: `trace:${id}`,
      label: id,
      kind: "trace",
      trace_id: id,
    }));
    const graph: LineageGraph = {
      nodes,
      edges: [],
      total_nodes: 4,
      shown_nodes: 4,
      truncated: false,
      trace_id: "",
      scope: "fixture",
    };
    // When
    const actual = graphLayout(graph);
    // Then
    expect(actual).toStrictEqual({
      nodes: nodes.map((node, i) => ({
        id: node.id,
        data: node,
        position: [
          { x: 0, y: 0 },
          { x: 330, y: 0 },
          { x: 0, y: 140 },
          { x: 330, y: 140 },
        ][i],
      })),
      edges: [],
    });
  });

  it("Given a lexical cluster, When mapping it, Then connects exactly its members", () => {
    // Given
    const group = {
      id: "group",
      count: 2,
      trace_ids: ["a", "b"],
      terms: ["schema"],
      label: "schema",
    };
    // When
    const actual = clusterLayout(group);
    // Then
    expect(actual).toStrictEqual({
      nodes: [
        {
          id: "cluster:group",
          data: { kind: "cluster", label: "2 traces · schema" },
          position: { x: 140, y: 0 },
        },
        {
          id: "trace:a",
          data: { kind: "trace", label: "a", trace_id: "a" },
          position: { x: 0, y: 180 },
        },
        {
          id: "trace:b",
          data: { kind: "trace", label: "b", trace_id: "b" },
          position: { x: 280, y: 180 },
        },
      ],
      edges: [
        {
          id: "cluster:group:trace:a",
          source: "cluster:group",
          target: "trace:a",
          label: "member",
        },
        {
          id: "cluster:group:trace:b",
          source: "cluster:group",
          target: "trace:b",
          label: "member",
        },
      ],
    });
  });
});
