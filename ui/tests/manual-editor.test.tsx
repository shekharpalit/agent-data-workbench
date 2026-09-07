import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../src/api";
import type { Investigation, ResearchResult } from "../src/contracts";
import { ManualResearchEditor } from "../src/views/ManualResearchEditor";

const findingId = "10000000-0000-4000-8000-000000000001";
const evidence = {
  trace_id: "external/chat-1",
  pointer: "/answer",
  quote: "Try again",
};
const result: ResearchResult = {
  analysis: {
    summary: "Agent draft",
    findings: [
      {
        id: findingId,
        title: "Unhelpful retry",
        category: "failure",
        confidence: "observation",
        explanation: "The answer repeats an instruction.",
        recommendation: "Clarify the next action.",
        evidence: [evidence],
      },
    ],
    cases: [
      {
        id: "10000000-0000-4000-8000-000000000002",
        title: "Explain the retry",
        finding_ids: [findingId],
        trace_ids: [evidence.trace_id],
        input: "What should I try?",
        required_context: ["Retry policy"],
        assertions: [
          { pointer: "/answer", operator: "contains", expected: "check" },
        ],
      },
    ],
    limitations: ["One observed exchange"],
  },
  signals: [
    {
      finding_id: findingId,
      kind: "friction",
      impact: "unknown",
      impact_reason: "No completion outcome was captured.",
      evidence: [evidence],
    },
  ],
  proposals: [
    {
      id: "10000000-0000-4000-8000-000000000003",
      finding_ids: [findingId],
      title: "Clarify retry context",
      kind: "context",
      hypothesis: "Additional instructions will help",
      expected_effect: "More actionable responses",
      evaluation_plan: "Run a reviewed task",
      edits: [
        {
          path: "policy.md",
          before: "Retry",
          after: "Check the connection, then retry",
        },
      ],
    },
  ],
  open_questions: ["Did the retry succeed?"],
};
const item: Investigation = {
  id: "10000000-0000-4000-8000-000000000004",
  created_at: "2026-09-07T00:00:00Z",
  question: "Review retries",
  status: "paused",
  error: null,
  source: { total: 1 },
  protocol_version: "0.4",
  mode: "research",
  active: false,
  session: null,
  coverage: { total: 1, retrieved: 1, completed: 0, failed: 0, pending: 1 },
  journal: { items: [], total: 0, next_offset: null },
  attachments: [],
  result,
};
function wrap(value: Investigation = item) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = (next: Investigation) => (
    <QueryClientProvider client={client}>
      <ManualResearchEditor item={next} />
    </QueryClientProvider>
  );
  const rendered = render(view(value));
  return { refresh: (next: Investigation) => rendered.rerender(view(next)) };
}
afterEach(() => vi.restoreAllMocks());

describe("manual research editor", () => {
  it("Given an agent draft, When a human edits and publishes through polling, Then retains all linked outputs and local changes", async () => {
    // Given
    const publish = vi
      .spyOn(api, "publishResearch")
      .mockResolvedValueOnce({
        id: item.id,
        status: "paused",
        coverage: item.coverage,
      })
      .mockResolvedValueOnce({
        id: item.id,
        status: "complete",
        coverage: item.coverage,
      });
    const user = userEvent.setup();
    const view = wrap();
    // When
    await user.click(screen.getByRole("button", { name: "Edit findings" }));
    await user.clear(screen.getByLabelText("Research summary"));
    await user.type(
      screen.getByLabelText("Research summary"),
      "Human review of retries",
    );
    await user.clear(screen.getByLabelText("Finding title"));
    await user.type(
      screen.getByLabelText("Finding title"),
      "Retry instruction lacks a next step",
    );
    await user.click(
      screen.getByRole("button", { name: "Save findings draft" }),
    );
    await screen.findByText(
      "Draft saved. You can continue researching before publishing.",
    );
    const refreshed = {
      ...result,
      open_questions: [...result.open_questions, "Is this tool-specific?"],
      analysis: { ...result.analysis, summary: "Server refresh" },
    };
    view.refresh({ ...item, result: refreshed });
    const summaryBeforePublication = (
      screen.getByLabelText("Research summary") as HTMLTextAreaElement
    ).value;
    const linkedFindingCanBeRemoved = !(
      screen.getByRole("button", {
        name: "Remove finding",
      }) as HTMLButtonElement
    ).disabled;
    await user.click(
      screen.getByRole("button", { name: "Publish final findings" }),
    );
    // Then
    const editedAnalysis = {
      ...result.analysis,
      summary: "Human review of retries",
      findings: [
        {
          ...result.analysis.findings[0]!,
          title: "Retry instruction lacks a next step",
        },
      ],
    };
    expect({
      calls: publish.mock.calls,
      summaryBeforePublication,
      linkedFindingCanBeRemoved,
      editorVisible:
        screen.queryByRole("button", { name: "Publish final findings" }) !==
        null,
    }).toStrictEqual({
      calls: [
        [item.id, { ...result, analysis: editedAnalysis }, false],
        [item.id, { ...refreshed, analysis: editedAnalysis }, true],
      ],
      summaryBeforePublication: "Human review of retries",
      linkedFindingCanBeRemoved: false,
      editorVisible: false,
    });
  });

  it("Given a new finding with repeated citations, When evidence validation fails, Then retains the entire draft for correction and retry", async () => {
    // Given
    const newId = "10000000-0000-4000-8000-000000000005";
    vi.spyOn(crypto, "randomUUID").mockReturnValue(newId);
    const publish = vi
      .spyOn(api, "publishResearch")
      .mockRejectedValueOnce(new Error("Quote does not match the snapshot"))
      .mockResolvedValueOnce({
        id: item.id,
        status: "paused",
        coverage: item.coverage,
      });
    const user = userEvent.setup();
    wrap({ ...item, result: null });
    // When
    await user.click(screen.getByRole("button", { name: "Write findings" }));
    await user.type(
      screen.getByLabelText("Research summary"),
      "The user recovered after clarification.",
    );
    await user.click(screen.getByRole("button", { name: "Add finding" }));
    await user.type(
      screen.getByLabelText("Finding title"),
      "Clarification helped",
    );
    await user.selectOptions(screen.getByLabelText("Category"), "opportunity");
    await user.selectOptions(screen.getByLabelText("Confidence"), "hypothesis");
    await user.type(
      screen.getByLabelText("Explanation"),
      "The next message shows recovery.",
    );
    await user.type(
      screen.getByLabelText("Recommendation"),
      "Test the clarification step.",
    );
    await user.type(screen.getByLabelText("Trace ID"), evidence.trace_id);
    await user.type(screen.getByLabelText("JSON pointer"), evidence.pointer);
    await user.type(screen.getByLabelText("Exact quote"), "try again");
    await user.click(screen.getByRole("button", { name: "Add citation" }));
    await user.type(
      screen.getAllByLabelText("Trace ID")[1]!,
      "external/chat-2",
    );
    await user.type(screen.getAllByLabelText("JSON pointer")[1]!, "/answer");
    await user.type(screen.getAllByLabelText("Exact quote")[1]!, "That worked");
    await user.click(
      screen.getByRole("button", { name: "Save findings draft" }),
    );
    const error = (await screen.findByRole("alert")).textContent;
    const retained = {
      title: (screen.getByLabelText("Finding title") as HTMLInputElement).value,
      quotes: screen
        .getAllByLabelText("Exact quote")
        .map((field) => (field as HTMLTextAreaElement).value),
    };
    await user.clear(screen.getAllByLabelText("Exact quote")[0]!);
    await user.type(
      screen.getAllByLabelText("Exact quote")[0]!,
      evidence.quote,
    );
    await user.click(
      screen.getByRole("button", { name: "Save findings draft" }),
    );
    await screen.findByText(
      "Draft saved. You can continue researching before publishing.",
    );
    // Then
    const expected: ResearchResult = {
      analysis: {
        summary: "The user recovered after clarification.",
        findings: [
          {
            id: newId,
            title: "Clarification helped",
            category: "opportunity",
            confidence: "hypothesis",
            explanation: "The next message shows recovery.",
            recommendation: "Test the clarification step.",
            evidence: [
              evidence,
              {
                trace_id: "external/chat-2",
                pointer: "/answer",
                quote: "That worked",
              },
            ],
          },
        ],
        cases: [],
        limitations: [],
      },
      signals: [],
      proposals: [],
      open_questions: [],
    };
    const rejected = {
      ...expected,
      analysis: {
        ...expected.analysis,
        findings: [
          {
            ...expected.analysis.findings[0]!,
            evidence: [
              { ...evidence, quote: "try again" },
              expected.analysis.findings[0]!.evidence[1]!,
            ],
          },
        ],
      },
    };
    expect({ calls: publish.mock.calls, error, retained }).toStrictEqual({
      calls: [
        [item.id, rejected, false],
        [item.id, expected, false],
      ],
      error: "Quote does not match the snapshot",
      retained: {
        title: "Clarification helped",
        quotes: ["try again", "That worked"],
      },
    });
  });

  it("Given an unfinished complete pass, When final publication is rejected, Then keeps the summary editable", async () => {
    // Given
    const publish = vi
      .spyOn(api, "publishResearch")
      .mockRejectedValue(
        new Error(
          "Complete-pass processing still has pending or failed records",
        ),
      );
    const user = userEvent.setup();
    wrap({ ...item, mode: "complete" });
    // When
    await user.click(screen.getByRole("button", { name: "Edit findings" }));
    await user.click(
      screen.getByRole("button", { name: "Publish final findings" }),
    );
    const error = (await screen.findByRole("alert")).textContent;
    // Then
    expect({
      calls: publish.mock.calls,
      error,
      summary: (
        screen.getByLabelText("Research summary") as HTMLTextAreaElement
      ).value,
    }).toStrictEqual({
      calls: [[item.id, result, true]],
      error: "Complete-pass processing still has pending or failed records",
      summary: result.analysis.summary,
    });
  });

  it("Given a journal note, When saving fails then succeeds, Then retains the note for retry and clears only the saved content", async () => {
    // Given
    const checkpoint = vi
      .spyOn(api, "researchCheckpoint")
      .mockRejectedValueOnce(new Error("Could not save note"))
      .mockResolvedValueOnce(item.coverage);
    const user = userEvent.setup();
    wrap();
    // When
    await user.type(
      screen.getByLabelText("Journal note"),
      "Read the retry exchange; inspect tool failures next.",
    );
    await user.click(screen.getByRole("button", { name: "Save journal note" }));
    const error = (await screen.findByRole("alert")).textContent;
    const retained = (
      screen.getByLabelText("Journal note") as HTMLTextAreaElement
    ).value;
    await user.click(screen.getByRole("button", { name: "Save journal note" }));
    await screen.findByText("Note saved to the investigation journal.");
    // Then
    expect({
      calls: checkpoint.mock.calls,
      error,
      retained,
      finalText: (screen.getByLabelText("Journal note") as HTMLTextAreaElement)
        .value,
    }).toStrictEqual({
      calls: [
        [item.id, "Read the retry exchange; inspect tool failures next."],
        [item.id, "Read the retry exchange; inspect tool failures next."],
      ],
      error: "Could not save note",
      retained: "Read the retry exchange; inspect tool failures next.",
      finalText: "",
    });
  });

  it("Given a chart with named rows, When saving, Then rejects blank values and sends typed numbers without a model call", async () => {
    // Given
    const chart = {
      title: "Retry counts",
      description: "Manually reviewed exchanges",
      values: [
        { label: "Clarified", value: 3.5 },
        { label: "Unresolved", value: 0 },
      ],
    };
    const create = vi.spyOn(api, "createResearchChart").mockResolvedValue({
      id: "chart",
      title: chart.title,
      kind: "chart",
      filename: "chart.json",
      bytes: 123,
      chart,
    });
    const user = userEvent.setup();
    wrap();
    // When
    await user.click(screen.getByText("Create a chart"));
    await user.type(screen.getByLabelText("Chart title"), chart.title);
    await user.type(
      screen.getByLabelText("Chart description"),
      chart.description,
    );
    await user.type(screen.getByLabelText("Label 1"), "Clarified");
    await user.click(screen.getByRole("button", { name: "Save chart" }));
    const validation = (await screen.findByRole("alert")).textContent;
    const callsAfterValidation = create.mock.calls.length;
    await user.type(screen.getByLabelText("Value 1"), "3.5");
    await user.click(screen.getByRole("button", { name: "Add chart row" }));
    await user.type(screen.getByLabelText("Label 2"), "Unresolved");
    await user.type(screen.getByLabelText("Value 2"), "0");
    await user.click(screen.getByRole("button", { name: "Save chart" }));
    await screen.findByText("Chart saved to research outputs.");
    // Then
    expect({
      calls: create.mock.calls,
      callsAfterValidation,
      validation,
      title: (screen.getByLabelText("Chart title") as HTMLInputElement).value,
    }).toStrictEqual({
      calls: [[item.id, chart]],
      callsAfterValidation: 0,
      validation:
        "Each chart row needs a label and a finite value of zero or more.",
      title: "",
    });
  });

  it("Given unsaved human work, When an agent starts then pauses, Then preserves every editor field while disabling active controls", async () => {
    // Given
    const user = userEvent.setup();
    const view = wrap();
    await user.click(screen.getByRole("button", { name: "Edit findings" }));
    await user.clear(screen.getByLabelText("Research summary"));
    await user.type(
      screen.getByLabelText("Research summary"),
      "Unsaved human finding",
    );
    await user.type(
      screen.getByLabelText("Journal note"),
      "Follow up on missing context",
    );
    await user.click(screen.getByText("Create a chart"));
    await user.type(screen.getByLabelText("Chart title"), "Unsaved chart");
    await user.type(screen.getByLabelText("Label 1"), "Reviewed");
    await user.type(screen.getByLabelText("Value 1"), "7");
    // When
    view.refresh({ ...item, status: "running", active: true });
    const activeButtons = screen.queryAllByRole("button").length;
    const disabledWhileActive = screen
      .getByLabelText("Research summary")
      .matches(":disabled");
    view.refresh({ ...item, status: "paused", active: false });
    // Then
    expect({
      activeButtons,
      disabledWhileActive,
      summary: (
        screen.getByLabelText("Research summary") as HTMLTextAreaElement
      ).value,
      note: (screen.getByLabelText("Journal note") as HTMLTextAreaElement)
        .value,
      chart: {
        title: (screen.getByLabelText("Chart title") as HTMLInputElement).value,
        label: (screen.getByLabelText("Label 1") as HTMLInputElement).value,
        value: (screen.getByLabelText("Value 1") as HTMLInputElement).value,
      },
      disabledAfterPause: screen
        .getByLabelText("Research summary")
        .matches(":disabled"),
    }).toStrictEqual({
      activeButtons: 0,
      disabledWhileActive: true,
      summary: "Unsaved human finding",
      note: "Follow up on missing context",
      chart: { title: "Unsaved chart", label: "Reviewed", value: "7" },
      disabledAfterPause: false,
    });
  });

  it.each([
    { status: "complete", active: false },
    { status: "running", active: true },
  ])(
    "Given $status research, When displaying the editor, Then exposes no mutations",
    (state) => {
      // Given / When
      wrap({ ...item, ...state });
      // Then
      expect({
        buttons: screen.queryAllByRole("button"),
        fields: screen.queryAllByRole("textbox"),
      }).toStrictEqual({ buttons: [], fields: [] });
    },
  );
});
