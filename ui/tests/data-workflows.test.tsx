import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import type { Experiment, Trace } from "../src/contracts";
import type { ReactNode } from "react";
import { api } from "../src/api";
import { ImportsView } from "../src/views/Imports";
import { DatasetView } from "../src/views/Dataset";
import { ExperimentDetail } from "../src/views/Experiments";
import { HarborComparisonForm } from "../src/views/HarborComparison";
import { Conversation } from "../src/components/traces/Conversation";
import { traceMessages } from "../src/components/traces/presentation";
import { initialSearch } from "../src/state";

function show(element: ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {element}
    </QueryClientProvider>,
  );
}

it("Given a dataset preset, When explicitly selecting rows and importing, Then submits the complete source mapping and no implicit text limits", async () => {
  // Given
  vi.spyOn(api, "imports").mockResolvedValue([]);
  vi.spyOn(api, "jobs").mockResolvedValue([]);
  const request = vi
    .spyOn(api, "importDataset")
    .mockResolvedValue({ job_id: "job" });
  const user = userEvent.setup();
  show(<ImportsView navigate={vi.fn()} />);
  // When
  await user.click(
    screen.getByRole("button", { name: "Use SWE-rebench / OpenHands preset" }),
  );
  await user.type(screen.getByLabelText("Maximum rows (optional)"), "64");
  await user.click(screen.getByRole("button", { name: "Import dataset" }));
  await screen.findByText(
    "Import submitted. Progress and any errors appear above. Results refresh automatically.",
  );
  // Then
  expect(request.mock.calls).toStrictEqual([
    [
      {
        dataset: "nebius/SWE-rebench-openhands-trajectories",
        configuration: null,
        split: "train",
        revision: "main",
        id_pointer: "/trajectory_id",
        group_pointer: "/instance_id",
        stratum_pointer: "/repo",
        limit: 64,
      },
    ],
  ]);
});

it("Given 21 source groups, When reading the chart and paging, Then counts outcomes truthfully and lets every task be inspected", async () => {
  // Given
  const groups = Array.from({ length: 21 }, (_, index) => ({
    id: `group-${index}`,
    label: `Task ${index + 1}`,
    strata: ["repository"],
    count: 2,
    trace_ids: [`pass-${index}`, `fail-${index}`],
    outcomes: { Passed: 1, Failed: 1, Unknown: 0 },
  }));
  vi.spyOn(api, "datasetProfile").mockResolvedValue({
    eligible: 42,
    group_count: 21,
    groups,
    outcome_pointer: "/resolved",
    outcomes: [
      { value: "Passed", count: 21 },
      { value: "Failed", count: 21 },
      { value: "Unknown", count: 0 },
    ],
    scope: "Exact imported source groups.",
  });
  const onMembers = vi.fn();
  const user = userEvent.setup();
  show(
    <DatasetView
      query={initialSearch}
      navigate={vi.fn()}
      onMembers={onMembers}
    />,
  );
  // When
  const chart = await screen.findByRole("group", {
    name: "Recorded attempts by task",
  });
  await user.click(
    within(chart).getByRole("button", {
      name: "Task 1: 2 runs, 1 passed, 1 failed, 0 unknown",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Next tasks" }));
  await user.click(
    within(chart).getByRole("button", {
      name: "Task 21: 2 runs, 1 passed, 1 failed, 0 unknown",
    }),
  );
  // Then
  expect({
    selection: onMembers.mock.calls,
    passed: screen
      .getByRole("progressbar", { name: "Passed: 21" })
      .getAttribute("value"),
    shown: within(chart).getAllByRole("button").length,
  }).toStrictEqual({
    selection: [[["pass-0", "fail-0"]], [["pass-20", "fail-20"]]],
    passed: "21",
    shown: 1,
  });
});

it("Given a long OpenHands tool event, When searching the tail and expanding it, Then renders the complete original content", async () => {
  // Given
  const content = "tool evidence α ".repeat(5000) + "FINAL-EVENT-EVIDENCE";
  const trace: Trace = {
    trace_id: "attempt",
    data: {
      trajectory: [
        { role: "user", content: "Request" },
        {
          role: "tool",
          content,
          tool_calls: [{ function: { arguments: '{"enabled":false}' } }],
        },
      ],
    },
  };
  const user = userEvent.setup();
  show(<Conversation trace={trace} />);
  // When
  await user.type(
    screen.getByLabelText("Search within this complete trace"),
    "FINAL-EVENT-EVIDENCE",
  );
  await user.click(screen.getByText("tool"));
  // Then
  expect({
    content: screen.getByText(content, { normalizer: (text) => text })
      .textContent,
    pointers: traceMessages(trace).map((message) => message.pointer),
    matched: screen.getByText(
      "1 of 2 events match. Expanding an event shows all its content.",
    ).textContent,
  }).toStrictEqual({
    content,
    pointers: ["/trajectory/0", "/trajectory/1"],
    matched: "1 of 2 events match. Expanding an event shows all its content.",
  });
});

it("Given Harbor setup, When launching a comparison, Then sends both agent configurations and the explicit verifier threshold", async () => {
  // Given
  vi.spyOn(api, "runtime").mockResolvedValue({
    environment: "native",
    tools: [],
  });
  const request = vi
    .spyOn(api, "compareHarbor")
    .mockResolvedValue({ job_id: "job" });
  const user = userEvent.setup();
  show(<HarborComparisonForm taskId="task" navigate={vi.fn()} />);
  // When
  await user.type(
    screen.getByLabelText("Harbor task template directory"),
    "/tmp/template",
  );
  await user.type(screen.getByLabelText("baseline agent"), "my_agent:Baseline");
  await user.type(screen.getByLabelText("candidate agent"), "codex");
  await user.click(screen.getByLabelText("candidate use host Codex login"));
  await user.click(
    screen.getByRole("button", { name: "Run baseline & candidate" }),
  );
  await screen.findByText(
    "Comparison submitted. Open the completed result from the job bar, or inspect saved trials while it runs.",
  );
  // Then
  expect(request.mock.calls).toStrictEqual([
    [
      "task",
      {
        template_directory: "/tmp/template",
        baseline: {
          agent: "my_agent:Baseline",
          model: "",
          agent_kwargs: {},
          use_host_codex_login: false,
        },
        candidate: {
          agent: "codex",
          model: "",
          agent_kwargs: {},
          use_host_codex_login: true,
        },
        environment_type: "docker",
        repetitions: 1,
        reward_key: "reward",
        pass_threshold: 1,
        timeout: null,
      },
    ],
  ]);
});

it.each(["running", "complete"] as const)(
  "Given a %s experiment with an incomplete pair, When inspecting it, Then distinguishes provisional pairing from final invalid outcomes",
  async (status) => {
    // Given
    const counts = {
      passed: 0,
      failed: 0,
      invalid: 0,
      total: 0,
      valid: 0,
      pass_rate: null,
      recorded_cost_usd: null,
      cost_coverage: 0,
      mean_latency_seconds: null,
    };
    const experiment = {
      id: "experiment",
      status,
      split: "exploratory",
      repeats: 1,
      conclusion: "Harbor comparison",
      trials: [],
      summary: {
        baseline: counts,
        candidate: counts,
        improved: [],
        regressed: [],
        invalid_pairs: [{ task_id: "task", trial: 0 }],
        task_mean_delta: null,
        task_bootstrap_95_interval: null,
        uncertainty_note: "One source group",
      },
    } as unknown as Experiment;
    vi.spyOn(api, "artifact").mockResolvedValue(experiment);
    // When
    show(<ExperimentDetail id="experiment" navigate={vi.fn()} />);
    await screen.findByRole("heading", { name: "Paired outcomes" });
    // Then
    expect({
      provisional:
        screen.queryByText(
          /pair counts are provisional until both variants finish/,
        ) !== null,
      invalid: screen.queryByText(/1 invalid pairs/) !== null,
    }).toStrictEqual({
      provisional: status === "running",
      invalid: status === "complete",
    });
  },
);
