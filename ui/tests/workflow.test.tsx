import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "../src/api";
import type {
  CalibrationAttempt,
  CalibrationResolution,
  Improvement,
  Taxonomy,
  World,
} from "../src/workflow-contracts";
import { WorldEditor } from "../src/views/Worlds";
import { CalibrationAttemptDetail } from "../src/views/Calibration";
import { CoverageMapEditor } from "../src/views/BehavioralCoverage";
import {
  ImprovementDecision,
  ImprovementEditor,
} from "../src/views/Improvements";

const world: World = {
  id: "10000000-0000-4000-8000-000000000001",
  spec: {
    name: "Support",
    domain: "Tickets",
    description: "Authoritative ticket data",
    schemas: {
      ticket: {
        required: ["open"],
        properties: { open: { type: "boolean" } },
        retryLimit: 0,
      },
    },
    tools: [],
    relationships: ["Ticket belongs to account"],
    permissions: ["Owners may close tickets"],
    invariants: ["Unrelated tickets remain unchanged"],
    sources: ["schema.json"],
    unresolved_questions: [],
  },
  revision: 2,
  sha256: "world-hash",
  created_at: "2026-09-07",
  previous_id: "older",
  previous_sha256: "older-hash",
  review: { status: "draft", note: "" },
};
const taxonomy: Taxonomy = {
  id: "10000000-0000-4000-8000-000000000002",
  spec: {
    name: "Support behaviors",
    description: "Ticket handling",
    capabilities: [
      {
        id: "10000000-0000-4000-8000-000000000003",
        name: "Cancellation",
        description: "Handle cancellation before action",
        required_slices: ["Mid-conversation"],
      },
    ],
  },
  revision: 1,
  sha256: "taxonomy-hash",
  created_at: "2026-09-07",
  previous: null,
  review: { status: "accepted", note: "Reviewed", reviewer: "owner" },
};
const attempt: CalibrationAttempt = {
  task_id: "10000000-0000-4000-8000-000000000004",
  trial: 0,
  variant: "candidate",
  evidence_sha256: "exact-evidence-hash",
  labels: [],
  adjudications: [],
  evidence: {
    task: {
      id: "10000000-0000-4000-8000-000000000004",
      title: "Cancellation",
      purpose: "Check cancellation",
      behavior: "Cancellation",
      finding_ids: [],
      trace_ids: [],
      fidelity: "environment",
      input_json: "{}",
      context_sha256: "context",
      assumptions: [],
      missing_context: [],
      criteria: [],
      verifier_examples: [],
    },
    trial: {
      task_id: "10000000-0000-4000-8000-000000000004",
      trial: 0,
      variant: "candidate",
      grade: {
        status: "pass",
        checks: [{ reason: "Judge thinks cancellation worked" }],
      },
      execution: {
        output: { message: "Cancelled" },
        status: "completed",
        latency_seconds: 1,
        cost_usd: null,
      },
      artifacts: {},
      state: { ticket: { open: false } },
      runtime_evidence: {
        conversation: {
          turns: [
            {
              index: 0,
              user: { message: "Close ticket" },
              reply: { message: "Confirm?", output: {}, evidence: [] },
              status: "completed",
              error: null,
            },
            {
              index: 1,
              user: { message: "Cancel that" },
              reply: { message: "Cancelled", output: {}, evidence: [] },
              status: "completed",
              error: null,
            },
          ],
          stop_reason: "script_finished",
          session_id: "same-session",
        },
      },
    },
    provenance: {},
  },
};
const resolution: CalibrationResolution = {
  task_id: attempt.task_id,
  trial: 0,
  variant: "candidate",
  evidence_sha256: attempt.evidence_sha256,
  labels_sha256: "exact-label-set",
  grader_status: "pass",
  human_status: null,
  resolution: "unlabeled",
  reviewers: 0,
  latest_labels: [],
  adjudication: null,
};
const improvement: Improvement = {
  id: "10000000-0000-4000-8000-000000000005",
  name: "Respect cancellation",
  hypothesis: "Wait for confirmation",
  expected_behavior: "No mutation after cancellation",
  baseline: { sha256: "baseline" },
  candidate: { sha256: "candidate" },
  patch: "exact patch",
  trace_ids: [],
  task_ids: [],
  experiments: [{ id: "linked-run" }],
  decisions: [],
};
function wrap(child: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{child}</QueryClientProvider>,
  );
}
afterEach(() => vi.restoreAllMocks());

describe("human improvement workflows", () => {
  it("Given a prior world version with typed schemas, When revising its description, Then preserves shared knowledge and links the exact prior version", async () => {
    // Given
    const create = vi
      .spyOn(api, "createWorld")
      .mockResolvedValue({ ...world, id: "next-world" });
    const saved = vi.fn();
    const user = userEvent.setup();
    wrap(<WorldEditor previous={world} onSaved={saved} />);
    // When
    await user.clear(screen.getByLabelText("World description"));
    await user.type(
      screen.getByLabelText("World description"),
      "Updated domain contract",
    );
    await user.click(screen.getByRole("button", { name: "Save world draft" }));
    // Then
    expect({
      requests: create.mock.calls,
      saved: saved.mock.calls,
    }).toStrictEqual({
      requests: [
        [{ ...world.spec, description: "Updated domain contract" }, world.id],
      ],
      saved: [["next-world"]],
    });
  });
  it("Given an unreviewed actual attempt, When a human labels it, Then hides grader judgments first and binds the label to frozen evidence", async () => {
    // Given
    const label = vi.spyOn(api, "labelAttempt").mockResolvedValue({
      id: "calibration",
      name: "Review",
      revision: 2,
      created_at: "2026-09-07",
      snapshot: { experiment_id: "run", split: "validation" },
      attempts: [attempt],
    });
    const user = userEvent.setup();
    wrap(
      <CalibrationAttemptDetail
        calibrationId="calibration"
        attempt={attempt}
        resolution={resolution}
      />,
    );
    const before = {
      graderEvidence: screen.queryByText("Grader decisions") !== null,
      completeRecord:
        screen.queryByText("Complete frozen trial record") !== null,
      reveal:
        screen.queryByRole("button", { name: "Reveal grader result" }) !== null,
      turns: screen.getAllByText(/Turn [12]$/).map((e) => e.textContent),
    };
    // When
    await user.type(screen.getByLabelText("Reviewer"), "Domain owner");
    await user.selectOptions(screen.getByLabelText("Human outcome"), "fail");
    await user.selectOptions(
      screen.getByLabelText("Failure cause (optional)"),
      "grader_false_pass",
    );
    await user.type(
      screen.getByLabelText("Reason and evidence"),
      "Observed ticket was closed despite cancellation.",
    );
    await user.click(
      screen.getByRole("button", { name: "Save human assessment" }),
    );
    await screen.findByText(
      "Human label saved for this exact attempt evidence.",
    );
    // Then
    expect({
      before,
      requests: label.mock.calls,
      graderRevealed: screen.queryByText("Grader decisions") !== null,
    }).toStrictEqual({
      before: {
        graderEvidence: false,
        completeRecord: false,
        reveal: true,
        turns: ["Turn 1", "Turn 2"],
      },
      requests: [
        [
          "calibration",
          {
            task_id: attempt.task_id,
            trial: 0,
            variant: "candidate",
            evidence_sha256: "exact-evidence-hash",
            reviewer: "Domain owner",
            reviewer_kind: "human",
            failure_cause: "grader_false_pass",
            status: "fail",
            reason: "Observed ticket was closed despite cancellation.",
          },
        ],
      ],
      graderRevealed: true,
    });
  });
  it("Given conflicting human labels, When adjudicating, Then binds the decision to both evidence and the displayed label set", async () => {
    // Given
    const decide = vi.spyOn(api, "adjudicateAttempt").mockResolvedValue({
      id: "calibration",
      name: "Review",
      revision: 2,
      created_at: "2026-09-07",
      snapshot: { experiment_id: "run", split: "validation" },
      attempts: [attempt],
    });
    const user = userEvent.setup();
    wrap(
      <CalibrationAttemptDetail
        calibrationId="calibration"
        attempt={attempt}
        resolution={{ ...resolution, resolution: "disagreement", reviewers: 2 }}
      />,
    );
    // When
    await user.selectOptions(
      screen.getByLabelText("Review action"),
      "adjudicate",
    );
    await user.type(screen.getByLabelText("Reviewer"), "Lead");
    await user.selectOptions(screen.getByLabelText("Human outcome"), "invalid");
    await user.type(
      screen.getByLabelText("Reason and evidence"),
      "Observer service was unavailable.",
    );
    await user.click(
      screen.getByRole("button", { name: "Save human assessment" }),
    );
    await screen.findByText("Adjudication saved for this exact set of labels.");
    // Then
    expect({ requests: decide.mock.calls }).toStrictEqual({
      requests: [
        [
          "calibration",
          {
            task_id: attempt.task_id,
            trial: 0,
            variant: "candidate",
            evidence_sha256: "exact-evidence-hash",
            labels_sha256: "exact-label-set",
            reviewer: "Lead",
            reviewer_kind: "human",
            failure_cause: null,
            status: "invalid",
            reason: "Observer service was unavailable.",
          },
        ],
      ],
    });
  });
  it("Given an accepted capability, When a human maps a production trace, Then preserves its external ID and review provenance", async () => {
    // Given
    const map = vi
      .spyOn(api, "mapCoverage")
      .mockResolvedValue({ id: "mapping" });
    const user = userEvent.setup();
    wrap(<CoverageMapEditor taxonomy={taxonomy} />);
    // When
    await user.type(
      screen.getByLabelText("External trace ID"),
      "customer/chat:123",
    );
    await user.selectOptions(
      screen.getByLabelText("Capability"),
      taxonomy.spec.capabilities[0]!.id,
    );
    await user.selectOptions(
      screen.getByLabelText("Behavioral slice"),
      "Mid-conversation",
    );
    await user.type(
      screen.getByLabelText("Mapping rationale"),
      "The user cancelled during confirmation.",
    );
    await user.type(
      screen.getByLabelText("Evidence source reference"),
      "/messages/2",
    );
    await user.type(screen.getByLabelText("Mapping reviewer"), "Owner");
    await user.click(
      screen.getByRole("button", { name: "Save evidence mapping" }),
    );
    await screen.findByText(
      "Mapping saved for this taxonomy and exact source version.",
    );
    // Then
    expect({ requests: map.mock.calls }).toStrictEqual({
      requests: [
        [
          taxonomy.id,
          {
            kind: "trace",
            entity_id: "customer/chat:123",
            capability_id: taxonomy.spec.capabilities[0]!.id,
            slice: "Mid-conversation",
            rationale: "The user cancelled during confirmation.",
            source: "/messages/2",
            reviewer: "Owner",
          },
        ],
      ],
    });
  });
  it("Given two configured runner versions, When capturing a hypothesis, Then sends source configuration paths and evidence IDs without inventing a candidate", async () => {
    // Given
    const create = vi
      .spyOn(api, "createImprovement")
      .mockResolvedValue(improvement);
    const saved = vi.fn();
    const user = userEvent.setup();
    wrap(<ImprovementEditor improvements={[]} onSaved={saved} />);
    // When
    await user.type(screen.getByLabelText("Change name"), improvement.name);
    await user.type(
      screen.getByLabelText("Hypothesis"),
      improvement.hypothesis,
    );
    await user.type(
      screen.getByLabelText("Expected behavior"),
      improvement.expected_behavior,
    );
    await user.type(
      screen.getByLabelText("Baseline runner configuration path"),
      "/agent/baseline.json",
    );
    await user.type(
      screen.getByLabelText("Candidate runner configuration path"),
      "/agent/candidate.json",
    );
    await user.click(
      screen.getByRole("button", { name: "Capture exact candidate" }),
    );
    // Then
    expect({
      requests: create.mock.calls,
      saved: saved.mock.calls,
    }).toStrictEqual({
      requests: [
        [
          {
            name: improvement.name,
            hypothesis: improvement.hypothesis,
            expected_behavior: improvement.expected_behavior,
            baseline_path: "/agent/baseline.json",
            candidate_path: "/agent/candidate.json",
            trace_ids: [],
            task_ids: [],
          },
        ],
      ],
      saved: [
        [improvement.id, "/agent/baseline.json", "/agent/candidate.json"],
      ],
    });
  });
  it("Given linked and unrelated experiments, When recording a decision, Then permits only a completed linked experiment and retains human reasoning", async () => {
    // Given
    const decide = vi
      .spyOn(api, "decideImprovement")
      .mockResolvedValue(improvement);
    const user = userEvent.setup();
    wrap(
      <ImprovementDecision
        improvement={improvement}
        experiments={[
          { id: "linked-run", status: "complete", split: "validation" },
          { id: "unrelated", status: "complete", split: "validation" },
          { id: "pending", status: "running", split: "optimization" },
        ]}
      />,
    );
    const options = Array.from(
      (
        screen.getByLabelText(
          "Completed linked experiment",
        ) as HTMLSelectElement
      ).options,
    ).map((o) => o.value);
    // When
    await user.selectOptions(
      screen.getByLabelText("Completed linked experiment"),
      "linked-run",
    );
    await user.selectOptions(
      screen.getByLabelText("Improvement decision"),
      "reject",
    );
    await user.type(screen.getByLabelText("Decision reviewer"), "Owner");
    await user.type(
      screen.getByLabelText("Decision reasoning"),
      "Regressed clarification on fresh cases.",
    );
    await user.click(
      screen.getByRole("button", { name: "Save improvement decision" }),
    );
    await screen.findByText(
      "Decision recorded with the experiment evidence. Apply the change through your normal development workflow.",
    );
    // Then
    expect({ options, requests: decide.mock.calls }).toStrictEqual({
      options: ["", "linked-run"],
      requests: [
        [
          {
            id: improvement.id,
            experiment_id: "linked-run",
            decision: "reject",
            reviewer: "Owner",
            reason: "Regressed clarification on fresh cases.",
          },
        ],
      ],
    });
  });
});
