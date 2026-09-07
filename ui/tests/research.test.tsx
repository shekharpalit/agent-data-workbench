import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, ApiClient } from "../src/api";
import type { Investigation } from "../src/contracts";
import { ResearchControls } from "../src/views/ResearchControls";
import { InvestigationDetail } from "../src/views/Investigations";

const item: Investigation = {
  id: "synthetic-investigation",
  created_at: "2026-09-07T00:00:00Z",
  question: "Review failures",
  status: "paused",
  active: false,
  error: null,
  protocol_version: "0.4",
  mode: "complete",
  source: { total: 200 },
  session: { backend: "claude", model: "selected", id: "native-session" },
  coverage: {
    total: 200,
    retrieved: 100,
    completed: 90,
    failed: 10,
    pending: 100,
  },
  journal: { items: [], total: 0, next_offset: null },
  attachments: [],
  result: {
    analysis: {
      summary: "Intermediate finding",
      findings: [],
      limitations: [],
    },
    signals: [],
    proposals: [],
    open_questions: [],
  },
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

describe("native research", () => {
  it("Given a new investigation, When choosing complete mode, Then submits scope without a call limit", async () => {
    // Given
    const invoke = vi
      .spyOn(api, "investigate")
      .mockResolvedValue({ job_id: "job" });
    const user = userEvent.setup();
    wrap(<ResearchControls />);
    // When
    await user.selectOptions(
      screen.getByLabelText("Analysis mode"),
      "complete",
    );
    await user.click(
      screen.getByLabelText("Exclude reserved final evaluation data"),
    );
    await user.click(screen.getByRole("button", { name: "Investigate" }));
    // Then
    expect(invoke.mock.calls).toStrictEqual([
      [
        {
          question:
            "Which failures and successful recoveries should we learn from?",
          backend: "codex",
          model: "",
          mode: "complete",
          exclude_final: true,
        },
      ],
    ]);
  });
  it("Given a partial result and saved Claude session, When resuming, Then retains the provider and session settings", async () => {
    // Given
    const invoke = vi
      .spyOn(api, "investigate")
      .mockResolvedValue({ job_id: "job" });
    vi.spyOn(api, "artifact").mockResolvedValue(item);
    vi.spyOn(api, "researchJournal").mockResolvedValue(item.journal);
    vi.spyOn(api, "researchOutcomes").mockResolvedValue({
      records: [],
      next_cursor: null,
    });
    const user = userEvent.setup();
    wrap(<InvestigationDetail id={item.id} navigate={() => {}} />);
    // When
    await user.click(
      await screen.findByRole("button", { name: "Resume investigation" }),
    );
    // Then
    expect({
      calls: invoke.mock.calls,
      partial: screen.getByText("Intermediate finding").textContent,
    }).toStrictEqual({
      calls: [[{ resume: item.id }]],
      partial: "Intermediate finding",
    });
  });
  it("Given a research attachment, When downloading, Then authenticates the request and preserves file bytes", async () => {
    // Given
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("saved report"));
    const client = new ApiClient(() => "local-token", transport);
    // When
    const blob = await client.researchFile("investigation", "artifact");
    // Then
    expect({
      text: await blob.text(),
      calls: transport.mock.calls,
    }).toStrictEqual({
      text: "saved report",
      calls: [
        [
          "/api/investigation/file?id=investigation&artifact=artifact",
          { headers: { Authorization: "Bearer local-token" } },
        ],
      ],
    });
  });
});
