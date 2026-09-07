import { describe, expect, it } from "vitest";
import {
  filterValue,
  graphLayout,
  initialSearch,
  nodeRoute,
  searchReducer,
} from "../src/state";
import type { LineageGraph } from "../src/contracts";

describe("search state", () => {
  it("Given a paged search, When filters change, Then resets only pagination", () => {
    // Given
    const previous = { ...initialSearch, offset: 40, stratum: "support" };
    // When
    const actual = searchReducer(previous, {
      type: "apply",
      query: { ...previous, text: "refund" },
    });
    // Then
    expect(actual).toStrictEqual({
      text: "refund",
      stratum: "support",
      filters: [],
      sort: "trace_id",
      direction: "asc",
      limit: 20,
      offset: 0,
      trace_ids: null,
    });
  });
  it("Given a search, When a cluster is selected, Then retains filters and restricts membership", () => {
    // Given
    const previous = { ...initialSearch, text: "refund", offset: 20 };
    // When
    const actual = searchReducer(previous, {
      type: "cluster",
      ids: ["run-1", "run-7"],
    });
    // Then
    expect(actual).toStrictEqual({
      text: "refund",
      stratum: "",
      filters: [],
      sort: "trace_id",
      direction: "asc",
      limit: 20,
      offset: 0,
      trace_ids: ["run-1", "run-7"],
    });
  });
  it("Given different value types, When building filters, Then preserves JSON types", () => {
    // Given
    const inputs = {
      text: "declined",
      number: "42",
      boolean: "true",
      literal: "42",
    };
    // When
    const actual = {
      text: filterValue("equals", inputs.text),
      number: filterValue("gte", inputs.number),
      boolean: filterValue("equals", inputs.boolean),
      literal: filterValue("contains", inputs.literal),
      missing: filterValue("missing", ""),
    };
    // Then
    expect(actual).toStrictEqual({
      text: '"declined"',
      number: "42",
      boolean: "true",
      literal: '"42"',
      missing: "null",
    });
  });
});

describe("evidence graph", () => {
  it("Given recorded lineage, When laying it out, Then retains links and removes dangling edges", () => {
    // Given
    const graph: LineageGraph = {
      nodes: [
        { id: "trace:t1", kind: "trace", label: "t1", trace_id: "t1" },
        { id: "task:T1", kind: "task", label: "Task", artifact_id: "T1" },
      ],
      edges: [
        {
          id: "e1",
          source: "trace:t1",
          target: "task:T1",
          label: "derived from",
        },
        { id: "e2", source: "missing", target: "task:T1", label: "invalid" },
      ],
      total_nodes: 2,
      shown_nodes: 2,
      truncated: false,
      trace_id: "",
      scope: "fixture",
    };
    // When
    const actual = graphLayout(graph);
    // Then
    expect(actual).toStrictEqual({
      nodes: [
        {
          id: "trace:t1",
          data: { id: "trace:t1", kind: "trace", label: "t1", trace_id: "t1" },
          position: { x: 0, y: 0 },
        },
        {
          id: "task:T1",
          data: {
            id: "task:T1",
            kind: "task",
            label: "Task",
            artifact_id: "T1",
          },
          position: { x: 660, y: 0 },
        },
      ],
      edges: [
        {
          id: "e1",
          source: "trace:t1",
          target: "task:T1",
          label: "derived from",
        },
      ],
    });
  });
  it("Given a finding node, When opening its evidence, Then routes to its investigation", () => {
    // Given
    const node = {
      id: "finding:I1:F1",
      kind: "finding" as const,
      label: "Observed failure",
      artifact_id: "I1",
    };
    // When
    const actual = nodeRoute(node);
    // Then
    expect(actual).toStrictEqual({ view: "investigations", id: "I1" });
  });
});
