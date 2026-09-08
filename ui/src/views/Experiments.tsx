import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrialEvidence } from "./TrialEvidence";
import { api } from "../api";
import type { Experiment, Route, Trial } from "../contracts";
import {
  Badge,
  Bars,
  Card,
  Details,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";

export function ExperimentsView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["artifacts", "experiments"],
    queryFn: ({ signal }) => api.artifacts("experiments", signal),
  });
  if (!request.data) return <ResourceState error={request.error} />;
  return (
    <Card title="Measure a change">
      <p className="muted">
        Run a Harbor comparison from an accepted task, or run a reviewed suite
        from Improvements. Inspect paired outcomes, verifier evidence and
        regressions here.
      </p>
      {[...request.data]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((experiment) => (
          <div className="item" key={experiment.id}>
            <div className="item-head">
              <h3>{experiment.conclusion}</h3>
              <Badge value={experiment.split} />
            </div>
            <p className="muted">
              {experiment.suite_id || "Reviewed Harbor task"} ·{" "}
              {experiment.repeats} repeats · {experiment.status}
            </p>
            <button
              className="ghost"
              onClick={() =>
                navigate({ view: "experiments", id: experiment.id })
              }
            >
              Inspect experiment →
            </button>
          </div>
        ))}
      {!request.data.length && (
        <p>
          No experiments yet. Start with an accepted task suite and two target
          configurations.
        </p>
      )}
    </Card>
  );
}
export function ExperimentDetail({
  id,
  navigate,
}: {
  id: string;
  navigate: (route: Route) => void;
}) {
  const request = useQuery<Experiment>({
    queryKey: ["experiment", id],
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
    queryFn: ({ signal }) => api.artifact("experiments", id, signal),
  });
  const [selected, setSelected] = useState<Trial | null>(null);
  if (!request.data) return <ResourceState error={request.error} />;
  const experiment = request.data,
    summary = experiment.summary;
  return (
    <>
      <button
        className="ghost breadcrumb"
        onClick={() => navigate({ view: "experiments" })}
      >
        ← Experiments
      </button>
      <Card title={experiment.conclusion}>
        {experiment.scope && <p className="scope-note">{experiment.scope}</p>}
        <div className="pill-group">
          <Badge value={experiment.split} />
          <Badge value={experiment.status} />
        </div>
        <p>
          {experiment.suite_id || "Reviewed Harbor task"} · {experiment.repeats}{" "}
          paired repeats
        </p>
      </Card>
      {summary.baseline && summary.candidate ? (
        <>
          <div className="grid two">
            {(["baseline", "candidate"] as const).map((variant) => {
              const value = summary[variant]!;
              return (
                <Card
                  key={variant}
                  title={variant === "baseline" ? "Baseline" : "Candidate"}
                >
                  <div className="metric">
                    {value.passed} / {value.valid}
                  </div>
                  <p>
                    {value.failed} failed · {value.invalid} invalid
                  </p>
                  <Bars
                    values={[
                      { value: "Pass", count: value.passed },
                      { value: "Fail", count: value.failed },
                      { value: "Invalid", count: value.invalid },
                    ]}
                    total={value.total}
                  />
                  <small>
                    Mean latency {value.mean_latency_seconds?.toFixed(3) ?? "—"}
                    s · cost{" "}
                    {value.recorded_cost_usd === null
                      ? "unavailable"
                      : `$${value.recorded_cost_usd}`}
                  </small>
                </Card>
              );
            })}
          </div>
          <Card title="Paired outcomes">
            <p>
              {summary.improved.length} improvements ·{" "}
              {summary.regressed.length} regressions
              {experiment.status === "running"
                ? " · pair counts are provisional until both variants finish"
                : ` · ${summary.invalid_pairs.length} invalid pairs`}
            </p>
            <Table
              headings={["Task", "Trial", "Variant", "Outcome", "Evidence"]}
              rows={experiment.trials.map((trial, index) => ({
                key: String(index),
                cells: [
                  <button
                    key="task"
                    className="ghost"
                    onClick={() =>
                      navigate({ view: "tasks", id: trial.task_id })
                    }
                  >
                    {trial.task_title || trial.task_id}
                  </button>,
                  trial.trial + 1,
                  trial.variant,
                  <Badge key="status" value={trial.grade.status} />,
                  <button
                    key="inspect"
                    className="ghost"
                    onClick={() => {
                      setSelected(trial);
                      document
                        .getElementById("trial-evidence")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    Inspect
                  </button>,
                ],
              }))}
            />
          </Card>
          <Card
            title={
              selected
                ? `${selected.task_id} · ${selected.variant}`
                : "Trial evidence"
            }
          >
            <div id="trial-evidence">
              {selected ? (
                <>
                  <TrialEvidence trial={selected} />
                  {selected.trace_ids?.map((traceId) => (
                    <button
                      key={traceId}
                      className="secondary"
                      onClick={() => navigate({ view: "traces", id: traceId })}
                    >
                      Inspect generated trace →
                    </button>
                  ))}
                </>
              ) : (
                <p className="muted">
                  Select a trial to inspect actual output, captured artifacts
                  and criterion decisions.
                </p>
              )}
            </div>
          </Card>
          <Card title="Uncertainty and scope">
            <p>{summary.uncertainty_note}</p>
            <p>
              Task-mean change:{" "}
              {summary.task_mean_delta === null
                ? "unavailable"
                : `${(summary.task_mean_delta * 100).toFixed(1)} percentage points`}
            </p>
            <p>
              95% interval:{" "}
              {summary.task_bootstrap_95_interval
                ? summary.task_bootstrap_95_interval
                    .map((value) => (value * 100).toFixed(1))
                    .join(" to ") + " points"
                : "insufficient independent source groups"}
            </p>
            {!!experiment.previously_investigated_tasks?.length && (
              <p className="scope-note">
                {experiment.previously_investigated_tasks.length} tasks use
                previously investigated traces. This is not an unseen-data
                estimate.
              </p>
            )}
          </Card>
        </>
      ) : (
        <Card title="Incomplete experiment">
          <JsonView value={experiment.trials} />
        </Card>
      )}
      <Details title="Recorded configurations and lineage">
        <JsonView
          value={{
            baseline: experiment.baseline,
            candidate: experiment.candidate,
            judge: experiment.judge,
            context_sha256: experiment.context_sha256,
            suite_sha256: experiment.suite_sha256,
            host: experiment.host,
          }}
        />
      </Details>
    </>
  );
}
