import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import type { ClusterResult, LineageGraph } from "../src/contracts";
import { initialSearch, graphLayout } from "../src/state";
import { ClustersView } from "../src/views/Clusters";
import GraphView from "../src/views/Graph";
import { SearchView } from "../src/views/Search";

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
    await user.click(await screen.findByRole("button", { name: "1. schema" }));
    await user.click(
      screen.getByRole("button", { name: "Inspect ungrouped traces →" }),
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
      navigation: [],
      members: [[["scan-a", "scan-b"]], [["scan-c"]]],
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

  it("Given traces without recorded links, When opening lineage, Then shows an honest empty state without a meaningless network", async () => {
    // Given
    vi.spyOn(api, "graph").mockResolvedValue({
      nodes: [
        { id: "trace:a", kind: "trace", label: "Source run", trace_id: "a" },
      ],
      edges: [],
      total_nodes: 1,
      shown_nodes: 1,
      truncated: false,
      trace_id: "a",
      scope: "Saved relationships only.",
    });
    const navigate = vi.fn();
    const user = userEvent.setup();
    renderQuery(
      <GraphView
        traceId="a"
        query={initialSearch}
        onMembers={vi.fn()}
        navigate={navigate}
      />,
    );
    // When
    await user.click(
      await screen.findByRole("button", { name: "Start an investigation →" }),
    );
    // Then
    expect({
      network: screen.queryByRole("region", { name: "Evidence lineage graph" }),
      navigation: navigate.mock.calls,
    }).toStrictEqual({
      network: null,
      navigation: [[{ view: "investigations" }]],
    });
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
});

it.each([
  { text: "evidence ".repeat(1000) + "final event", enabled: true },
  null,
])(
  "Given a complete input beyond page 10000, When expanding and paging, Then preserves its content and type and reaches later records",
  async (input) => {
    // Given
    const query = { ...initialSearch, offset: 10000 };
    vi.spyOn(api, "search").mockResolvedValue({
      query,
      eligible: 10021,
      selected: 1,
      ids: ["long-record"],
      records: [{ trace_id: "long-record", data: { input } }],
      strata: {},
      source_sha256: "fixture",
    });
    vi.spyOn(api, "distribution").mockResolvedValue({
      pointer: "/tool_result/status",
      eligible: 10021,
      missing_or_non_scalar: 10021,
      counts: [],
      distinct: 0,
      numeric_count: 0,
      mean: null,
      minimum: null,
      maximum: null,
    });
    const onQuery = vi.fn();
    const user = userEvent.setup();
    renderQuery(
      <SearchView query={query} onQuery={onQuery} navigate={vi.fn()} />,
    );
    // When
    await user.click(await screen.findByText("Read input / request"));
    const complete = screen.getByText(JSON.stringify(input, null, 2), {
      normalizer: (text) => text,
    }).textContent;
    await user.click(screen.getByRole("button", { name: /^Next$/ }));
    // Then
    expect({ content: complete, queries: onQuery.mock.calls }).toStrictEqual({
      content: JSON.stringify(input, null, 2),
      queries: [[{ ...query, offset: 10020 }]],
    });
  },
);
