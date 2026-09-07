import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, ApiClient } from "../src/api";
import type { Investigation } from "../src/contracts";
import { InvestigationsView } from "../src/views/Investigations";
import {
  ResearchSnapshot,
  SnapshotCitation,
} from "../src/views/ResearchSnapshot";

const item: Investigation = {
  id: "f1fbb8aa-718f-4ffa-a03d-486bfb352e91",
  created_at: "2026-09-07T00:00:00Z",
  question: "Understand failures",
  status: "paused",
  error: null,
  protocol_version: "0.4",
  active: false,
  mode: "complete",
  session: null,
  source: { total: 2 },
  coverage: { total: 2, retrieved: 0, completed: 0, pending: 2, failed: 0 },
  journal: { items: [], total: 0, next_offset: null },
  result: null,
};
function wrap(children: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  );
}
afterEach(() => vi.restoreAllMocks());

describe("manual research", () => {
  it("Given a question, When starting manual research, Then opens its workspace without an agent request", async () => {
    // Given
    vi.spyOn(api, "artifacts").mockResolvedValue([]);
    const create = vi.spyOn(api, "createResearch").mockResolvedValue(item);
    const agent = vi.spyOn(api, "investigate");
    const navigate = vi.fn();
    const user = userEvent.setup();
    wrap(<InvestigationsView navigate={navigate} />);
    // When
    await user.clear(screen.getByLabelText("What do you want to understand?"));
    await user.type(
      screen.getByLabelText("What do you want to understand?"),
      item.question,
    );
    await user.selectOptions(
      screen.getByLabelText("Analysis mode"),
      "complete",
    );
    await user.click(
      screen.getByLabelText("Exclude reserved final evaluation data"),
    );
    await user.click(
      screen.getByRole("button", { name: "Start manual research" }),
    );
    // Then
    expect({
      create: create.mock.calls,
      agent: agent.mock.calls,
      navigate: navigate.mock.calls,
      provider: screen.queryByLabelText("Analyzer"),
    }).toStrictEqual({
      create: [
        [{ question: item.question, mode: "complete", exclude_final: true }],
      ],
      agent: [],
      navigate: [[{ view: "investigations", id: item.id }]],
      provider: null,
    });
  });
  it("Given paged snapshot data, When reading a field and saving a typed outcome, Then keeps the investigation and original trace identity", async () => {
    // Given
    const record = {
      trace_id: "external/#1",
      stratum: "chat",
      group_id: "source",
      preview: "initial",
      total_chars: 12,
      truncated: false,
      status: "pending",
    };
    const search = vi.spyOn(api, "searchResearch").mockResolvedValue({
      records: [record],
      next_cursor: "external/#1",
      coverage: item.coverage,
    });
    const read = vi
      .spyOn(api, "researchTrace")
      .mockImplementation(async (_, traceId, pointer, offset) => ({
        trace_id: traceId,
        pointer,
        offset,
        content: offset ? "rest" : "start",
        total_chars: 9,
        next_offset: offset ? null : 5,
      }));
    const save = vi
      .spyOn(api, "recordResearch")
      .mockResolvedValue({ ...item.coverage, completed: 1, pending: 1 });
    const user = userEvent.setup();
    wrap(<ResearchSnapshot item={item} />);
    // When
    await user.type(screen.getByLabelText("Search this snapshot"), "error");
    await user.click(screen.getByLabelText("Only pending or failed records"));
    await user.click(screen.getByRole("button", { name: "Search records" }));
    await user.click(
      screen.getByRole("button", { name: "Next matching records →" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "external/#1" }),
    );
    await user.type(
      screen.getByLabelText("JSON pointer (blank for whole record)"),
      "/output",
    );
    await user.click(screen.getByRole("button", { name: "Read field" }));
    await user.click(screen.getByRole("button", { name: "Read next part →" }));
    await user.click(screen.getByLabelText("Use a structured JSON outcome"));
    await user.clear(screen.getByLabelText("Outcome JSON object"));
    await user.paste('{"correct":false,"retries":2,"reason":null}');
    await user.click(
      screen.getByRole("button", { name: "Save record outcome" }),
    );
    await screen.findByText(
      "Outcome saved. You can revisit and update it before publishing.",
    );
    // Then
    expect({
      query: search.mock.calls.at(-1)?.slice(0, 2),
      read: read.mock.calls.at(-1)?.slice(0, 4),
      outcome: save.mock.calls,
    }).toStrictEqual({
      query: [
        item.id,
        {
          text: "error",
          stratum: "",
          pending_only: true,
          after: "external/#1",
        },
      ],
      read: [item.id, "external/#1", "/output", 5],
      outcome: [
        [
          item.id,
          [
            {
              trace_id: "external/#1",
              output: { correct: false, retries: 2, reason: null },
              error: null,
              method: "Human review",
            },
          ],
        ],
      ],
    });
  });
  it("Given failed review, When saving a failure, Then keeps it unresolved rather than recording completion", async () => {
    // Given
    vi.spyOn(api, "searchResearch").mockResolvedValue({
      records: [
        {
          trace_id: "trace",
          stratum: "",
          group_id: "",
          preview: "",
          total_chars: 1,
          truncated: false,
          status: "pending",
        },
      ],
      next_cursor: null,
      coverage: item.coverage,
    });
    vi.spyOn(api, "researchTrace").mockResolvedValue({
      trace_id: "trace",
      pointer: "",
      content: "{}",
      offset: 0,
      total_chars: 2,
      next_offset: null,
    });
    const save = vi
      .spyOn(api, "recordResearch")
      .mockResolvedValue(item.coverage);
    const user = userEvent.setup();
    wrap(<ResearchSnapshot item={item} />);
    // When
    await user.click(await screen.findByRole("button", { name: "trace" }));
    await user.selectOptions(screen.getByLabelText("Review outcome"), "failed");
    await user.type(
      screen.getByLabelText("What prevented review?"),
      "Need the expected policy",
    );
    await user.click(
      screen.getByRole("button", { name: "Save record outcome" }),
    );
    // Then
    expect(save.mock.calls).toStrictEqual([
      [
        item.id,
        [
          {
            trace_id: "trace",
            output: null,
            error: "Need the expected policy",
            method: "Human review",
          },
        ],
      ],
    ]);
  });
  it("Given an authenticated local UI, When posting human work and reading an external trace ID, Then uses scoped JSON routes", async () => {
    // Given
    const transport = vi.fn<typeof fetch>().mockImplementation(
      async () =>
        new Response("{}", {
          headers: { "Content-Type": "application/json" },
        }),
    );
    const client = new ApiClient(() => "token", transport);
    // When
    await client.createResearch({
      question: "Why?",
      mode: "research",
      exclude_final: false,
    });
    await client.researchTrace("id", "id?/#&", "/messages/0/content", 16000);
    // Then
    expect(transport.mock.calls).toStrictEqual([
      [
        "/api/investigation/create",
        {
          method: "POST",
          headers: {
            Authorization: "Bearer token",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: "Why?",
            mode: "research",
            exclude_final: false,
          }),
        },
      ],
      [
        "/api/investigation/trace?id=id&trace_id=id%3F%2F%23%26&pointer=%2Fmessages%2F0%2Fcontent&offset=16000",
        { method: "GET", headers: { Authorization: "Bearer token" } },
      ],
    ]);
  });
  it("Given cited evidence, When opening its source, Then reads the frozen field rather than the live trace", async () => {
    // Given
    const evidence = {
      trace_id: "external",
      pointer: "/answer",
      quote: "original",
    };
    const read = vi.spyOn(api, "researchTrace").mockResolvedValue({
      ...evidence,
      content: "original",
      offset: 0,
      total_chars: 8,
      next_offset: null,
    });
    const live = vi.spyOn(api, "trace");
    const user = userEvent.setup();
    wrap(<SnapshotCitation item={item} evidence={evidence} />);
    // When
    await user.click(
      screen.getByRole("button", { name: "external · /answer" }),
    );
    await screen.findByText("original");
    // Then
    expect({
      read: read.mock.calls.map((call) => call.slice(0, 4)),
      live: live.mock.calls,
      save: screen.queryByRole("button", { name: "Save record outcome" }),
    }).toStrictEqual({
      read: [[item.id, "external", "/answer", 0]],
      live: [],
      save: null,
    });
  });
});
