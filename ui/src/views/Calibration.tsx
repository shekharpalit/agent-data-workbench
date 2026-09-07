import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { GradeStatus, Route } from "../contracts";
import type {
  Calibration,
  CalibrationAttempt,
  CalibrationResolution,
  CalibrationSummary,
  FailureCause,
} from "../workflow-contracts";
import {
  ActionButton,
  Badge,
  Card,
  Choice,
  Details,
  Field,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";
import { SelectField, useWorkflow } from "./WorkflowShared";
import { TrialEvidence } from "./TrialEvidence";

function attemptKey(attempt: {
  task_id: string;
  trial: number;
  variant: string;
}) {
  return `${attempt.task_id}/${attempt.trial}/${attempt.variant}`;
}
export function AttemptReview({
  calibrationId,
  attempt,
  resolution,
  onSaved,
}: {
  calibrationId: string;
  attempt: CalibrationAttempt;
  resolution: CalibrationResolution;
  onSaved?: () => void;
}) {
  const [reviewer, setReviewer] = useState("");
  const [status, setStatus] = useState<GradeStatus>("invalid");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<"label" | "adjudicate">("label");
  const [saved, setSaved] = useState("");
  const [cause, setCause] = useState<FailureCause | "">("");
  return (
    <Card title="Human assessment">
      <p>
        Assess this recorded attempt against its frozen task requirements.
        Resolve uncertain or unusable evidence as invalid.
      </p>
      <div className="stack">
        <Choice
          label="Review action"
          options={["label", "adjudicate"]}
          value={mode}
          onChange={setMode}
        />
        <div className="row">
          <Field label="Reviewer" value={reviewer} onChange={setReviewer} />
          <Choice
            label="Human outcome"
            value={status}
            options={["pass", "fail", "invalid"]}
            onChange={setStatus}
          />
        </div>
        <SelectField
          label="Failure cause (optional)"
          value={cause}
          onChange={(v) => setCause(v as FailureCause | "")}
          placeholder="Not classified"
          options={[
            "agent_capability",
            "missing_information",
            "harness",
            "environment",
            "grader_false_pass",
            "grader_false_fail",
            "leakage",
            "infrastructure",
            "other",
          ].map((id) => ({ id, label: id.replaceAll("_", " ") }))}
        />
        <Field
          label="Reason and evidence"
          value={reason}
          onChange={setReason}
          multiline
        />
        <ActionButton
          action={async () => {
            if (!reviewer.trim() || !reason.trim())
              throw new Error(
                "Enter a reviewer and a reason supported by this attempt.",
              );
            const label = {
              reviewer_kind: "human" as const,
              failure_cause: cause || null,
              task_id: attempt.task_id,
              trial: attempt.trial,
              variant: attempt.variant,
              evidence_sha256: attempt.evidence_sha256,
              reviewer,
              status,
              reason,
            };
            if (mode === "adjudicate")
              await api.adjudicateAttempt(calibrationId, {
                ...label,
                labels_sha256: resolution.labels_sha256,
              });
            else await api.labelAttempt(calibrationId, label);
            onSaved?.();
            setSaved(
              mode === "adjudicate"
                ? "Adjudication saved for this exact set of labels."
                : "Human label saved for this exact attempt evidence.",
            );
          }}
        >
          Save human assessment
        </ActionButton>
        {saved && <p role="status">{saved}</p>}
      </div>
      <Details title="Existing human labels and adjudication">
        <JsonView
          value={{
            labels: resolution.latest_labels,
            adjudication: resolution.adjudication,
          }}
        />
      </Details>
    </Card>
  );
}
function CalibrationMetrics({ summary }: { summary: CalibrationSummary }) {
  return (
    <>
      <div className="grid metrics">
        <Card title="Human-reviewed attempts">
          <div className="metric">
            {summary.resolved} / {summary.total}
          </div>
          <p>
            {summary.unlabeled} unlabeled · {summary.disagreements}{" "}
            disagreements
          </p>
        </Card>
        {(
          [
            ["false_pass", "False passes"],
            ["false_fail", "False failures"],
          ] as const
        ).map(([key, title]) => (
          <Card title={title} key={key}>
            <div className="metric">{summary[key].count}</div>
            <p>
              {summary[key].rate === null
                ? "No eligible human labels"
                : `${(summary[key].rate * 100).toFixed(1)}% of ${summary[key].denominator} eligible human ${key === "false_pass" ? "failures" : "passes"}`}
            </p>
          </Card>
        ))}
      </div>
      <Card title="Grader versus human decisions">
        <Table
          headings={["Grader ↓ / human →", "Pass", "Fail", "Invalid"]}
          rows={(["pass", "fail", "invalid"] as const).map((status) => ({
            key: status,
            cells: [
              status,
              summary.confusion_matrix[status].pass,
              summary.confusion_matrix[status].fail,
              summary.confusion_matrix[status].invalid,
            ],
          }))}
        />
        <p>
          {summary.invalid_disagreements} invalid disagreements ·{" "}
          {summary.adjudicated} adjudicated
        </p>
        {summary.failure_causes && (
          <Details title="Failure causes">
            <Table
              headings={["Cause", "Resolved attempts"]}
              rows={Object.entries(summary.failure_causes).map(
                ([cause, count]) => ({
                  key: cause,
                  cells: [cause.replaceAll("_", " "), count],
                }),
              )}
            />
            <p>{summary.cause_disagreements || 0} cause disagreements</p>
          </Details>
        )}
        <p className="scope-note">{summary.scope}</p>
      </Card>
    </>
  );
}
function CalibrationDetail({
  id,
  navigate,
}: {
  id: string;
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["calibration", id],
    queryFn: ({ signal }) => api.calibration(id, signal),
  });
  const [selected, setSelected] = useState("");
  if (!request.data) return <ResourceState error={request.error} />;
  const { calibration, summary } = request.data;
  const attempt = calibration.attempts.find((a) => attemptKey(a) === selected);
  const resolution = summary.attempts.find((a) => attemptKey(a) === selected);
  return (
    <>
      <Card title={calibration.name}>
        <p>
          Revision {calibration.revision} · {calibration.snapshot.split}{" "}
          attempts
        </p>
        <button
          className="ghost"
          onClick={() =>
            navigate({
              view: "experiments",
              id: calibration.snapshot.experiment_id,
            })
          }
        >
          Inspect source experiment →
        </button>
      </Card>
      <Details title="Show aggregate calibration results">
        <CalibrationMetrics summary={summary} />
      </Details>
      <Card title="Recorded attempts">
        <Table
          headings={[
            "Task",
            "Trial",
            "Variant",
            "Grader",
            "Human",
            "Review",
            "",
          ]}
          rows={summary.attempts.map((a) => ({
            key: attemptKey(a),
            cells: [
              calibration.attempts.find(
                (item) => attemptKey(item) === attemptKey(a),
              )?.evidence.task.title || a.task_id,
              a.trial + 1,
              a.variant,
              a.human_status ? (
                <Badge key="grade" value={a.grader_status} />
              ) : (
                "Hidden before labeling"
              ),
              a.human_status || "—",
              a.resolution,
              <button
                key="open"
                className="ghost"
                onClick={() => setSelected(attemptKey(a))}
              >
                Review attempt
              </button>,
            ],
          }))}
        />
      </Card>
      {attempt && resolution && (
        <CalibrationAttemptDetail
          key={selected}
          calibrationId={id}
          attempt={attempt}
          resolution={resolution}
        />
      )}
    </>
  );
}
export function CalibrationAttemptDetail({
  calibrationId,
  attempt,
  resolution,
}: {
  calibrationId: string;
  attempt: CalibrationAttempt;
  resolution: CalibrationResolution;
}) {
  const [revealed, setRevealed] = useState(resolution.human_status !== null);
  return (
    <>
      <Card title="Frozen task requirements">
        <h3>{attempt.evidence.task.title}</h3>
        <p>{attempt.evidence.task.purpose}</p>
        <p>{attempt.evidence.task.behavior}</p>
        <Details title="Task input, criteria and pinned environment">
          <JsonView value={attempt.evidence.task} />
        </Details>
      </Card>
      <Card title="Actual attempt evidence">
        <TrialEvidence trial={attempt.evidence.trial} showGrade={revealed} />
        {revealed && !!resolution.model_labels?.length && (
          <Details title="Model label suggestions">
            <JsonView value={resolution.model_labels} />
            <p className="muted">
              Model suggestions are retained separately from human calibration
              counts.
            </p>
          </Details>
        )}
        {!revealed && (
          <>
            <p className="muted">
              Grader judgments are hidden while you form an independent
              assessment.
            </p>
            <button className="secondary" onClick={() => setRevealed(true)}>
              Reveal grader result
            </button>
          </>
        )}
      </Card>
      <AttemptReview
        calibrationId={calibrationId}
        attempt={attempt}
        resolution={resolution}
        onSaved={() => setRevealed(true)}
      />
    </>
  );
}
export function CalibrationView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const workflow = useWorkflow();
  const experiments = useQuery({
    queryKey: ["artifacts", "experiments"],
    queryFn: ({ signal }) => api.artifacts("experiments", signal),
  });
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [experiment, setExperiment] = useState("");
  if (!workflow.data || !experiments.data)
    return <ResourceState error={workflow.error || experiments.error} />;
  return (
    <>
      <Card title="Calibrate graders with human review">
        <p>
          Label actual agent attempts, compare grader decisions, and adjudicate
          disagreements with evidence retained.
        </p>
        <div className="workflow-library">
          {workflow.data.calibrations.map((item: Calibration) => (
            <button
              key={item.id}
              className={
                selected === item.id ? "selected-artifact" : "secondary"
              }
              onClick={() => setSelected(item.id)}
            >
              {item.name}
              <span>
                Revision {item.revision} · {item.attempts.length} attempts
              </span>
            </button>
          ))}
        </div>
        <Details title="Start a calibration">
          <div className="stack">
            <Field label="Calibration name" value={name} onChange={setName} />
            <SelectField
              label="Recorded experiment"
              value={experiment}
              onChange={setExperiment}
              options={experiments.data
                .filter(
                  (e) =>
                    ["complete", "interrupted"].includes(e.status) &&
                    e.trials.length > 0,
                )
                .map((e) => ({
                  id: e.id,
                  label: `${e.conclusion} · ${e.split} · ${e.id}`,
                }))}
            />
            <ActionButton
              action={async () => {
                if (!name.trim() || !experiment)
                  throw new Error(
                    "Name the calibration and select an experiment with recorded attempts.",
                  );
                const saved = await api.createCalibration(experiment, name);
                setSelected(saved.id);
                setName("");
              }}
            >
              Create calibration
            </ActionButton>
          </div>
        </Details>
      </Card>
      {selected && (
        <CalibrationDetail key={selected} id={selected} navigate={navigate} />
      )}
    </>
  );
}
