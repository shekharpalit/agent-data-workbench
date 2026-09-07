import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Route } from "../contracts";
import type {
  Improvement,
  Workflow,
  WorkflowExperiment,
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
} from "../components/shared";
import { lines, SelectField, useWorkflow } from "./WorkflowShared";
export function ImprovementEditor({
  improvements,
  onSaved,
}: {
  improvements: Improvement[];
  onSaved: (id: string, baseline: string, candidate: string) => void;
}) {
  const [name, setName] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [expected, setExpected] = useState("");
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [traces, setTraces] = useState("");
  const [tasks, setTasks] = useState("");
  const [parent, setParent] = useState("");
  return (
    <Card title="Capture a proposed improvement">
      <p>
        Connect the failure hypothesis to the actual baseline and candidate
        source files. The workbench records the configurations, source hashes
        and patch for subsequent experiments.
      </p>
      <div className="stack">
        <Field label="Change name" value={name} onChange={setName} />
        <Field
          label="Hypothesis"
          value={hypothesis}
          onChange={setHypothesis}
          multiline
        />
        <Field
          label="Expected behavior"
          value={expected}
          onChange={setExpected}
          multiline
        />
        <div className="row">
          <Field
            label="Baseline runner configuration path"
            value={baseline}
            onChange={setBaseline}
          />
          <Field
            label="Candidate runner configuration path"
            value={candidate}
            onChange={setCandidate}
          />
        </div>
        <small>
          Use existing RunnerConfig JSON files on this computer. Their declared
          source files are captured with the change.
        </small>
        <Details title="Evidence and previous improvement">
          <Field
            label="Source trace IDs (one per line)"
            value={traces}
            onChange={setTraces}
            multiline
          />
          <Field
            label="Related task IDs (one per line)"
            value={tasks}
            onChange={setTasks}
            multiline
          />
          <SelectField
            label="Previous improvement"
            value={parent}
            onChange={setParent}
            placeholder="No previous improvement"
            options={improvements.map((i) => ({ id: i.id, label: i.name }))}
          />
        </Details>
        <ActionButton
          action={async () => {
            if (
              [name, hypothesis, expected, baseline, candidate].some(
                (v) => !v.trim(),
              )
            )
              throw new Error(
                "Complete the change, hypothesis, expected behavior and both runner paths.",
              );
            const result = await api.createImprovement({
              name,
              hypothesis,
              expected_behavior: expected,
              baseline_path: baseline,
              candidate_path: candidate,
              trace_ids: lines(traces),
              task_ids: lines(tasks),
              ...(parent ? { parent_id: parent } : {}),
            });
            onSaved(result.id, baseline, candidate);
          }}
        >
          Capture exact candidate
        </ActionButton>
      </div>
    </Card>
  );
}
function ExperimentRun({
  improvement,
  suites,
  initialPaths,
}: {
  improvement: Improvement;
  suites: Workflow["suites"];
  initialPaths: { baseline: string; candidate: string };
}) {
  const [suite, setSuite] = useState("");
  const [baseline, setBaseline] = useState(initialPaths.baseline);
  const [candidate, setCandidate] = useState(initialPaths.candidate);
  const [split, setSplit] = useState<WorkflowExperiment["split"]>("validation");
  const [repeats, setRepeats] = useState("1");
  const [seed, setSeed] = useState("0");
  const [judge, setJudge] = useState<"" | "codex" | "claude">("");
  const [judgeModel, setJudgeModel] = useState("");
  const [queued, setQueued] = useState(false);
  return (
    <Card title="Evaluate this exact change">
      <p>
        Use a reviewed suite and the runner files captured above. The backend
        verifies their identity before running the comparison.
      </p>
      <div className="stack">
        <SelectField
          label="Reviewed suite"
          value={suite}
          onChange={setSuite}
          options={suites.map((s) => ({
            id: s.id,
            label: `${s.name || s.id}${s.tasks ? ` · ${s.tasks.length} tasks` : ""}`,
          }))}
        />
        <div className="row">
          <Field
            label="Experiment baseline runner path"
            value={baseline}
            onChange={setBaseline}
          />
          <Field
            label="Experiment candidate runner path"
            value={candidate}
            onChange={setCandidate}
          />
        </div>
        <div className="row">
          <Choice
            label="Evaluation split"
            value={split}
            options={["optimization", "validation", "final"]}
            onChange={setSplit}
          />
          <Field
            label="Paired repeats"
            value={repeats}
            onChange={setRepeats}
            type="number"
            min={1}
          />
          <Field
            label="Random seed"
            value={seed}
            onChange={setSeed}
            type="number"
          />
        </div>
        <SelectField
          label="Semantic judge"
          value={judge}
          onChange={(v) => setJudge(v as typeof judge)}
          placeholder="Deterministic criteria only"
          options={[
            { id: "codex", label: "Codex" },
            { id: "claude", label: "Claude" },
          ]}
        />
        {judge && (
          <Field
            label="Judge model (optional)"
            value={judgeModel}
            onChange={setJudgeModel}
          />
        )}{" "}
        {split === "final" && (
          <p className="scope-note">
            The final split is consumed by this evaluation. Previously exposed
            source groups retain their exposure history.
          </p>
        )}
        <ActionButton
          action={async () => {
            if (
              !suite ||
              !baseline.trim() ||
              !candidate.trim() ||
              !repeats.trim() ||
              !Number.isInteger(Number(repeats)) ||
              Number(repeats) < 1 ||
              !seed.trim() ||
              !Number.isInteger(Number(seed))
            )
              throw new Error(
                "Select a suite, both runner paths, a positive repeat count and an integer seed.",
              );
            await api.runWorkflowExperiment({
              suite_id: suite,
              baseline_path: baseline,
              candidate_path: candidate,
              improvement_id: improvement.id,
              split,
              repeats: Number(repeats),
              seed: Number(seed),
              ...(judge
                ? { judge, ...(judgeModel ? { judge_model: judgeModel } : {}) }
                : {}),
            });
            setQueued(true);
          }}
        >
          Run paired experiment
        </ActionButton>
        {queued && (
          <p role="status">
            Experiment queued. Follow its progress in the job status, then
            refresh results.
          </p>
        )}
      </div>
    </Card>
  );
}
export function ImprovementDecision({
  improvement,
  experiments,
}: {
  improvement: Improvement;
  experiments: { id: string; status: string; split: string }[];
}) {
  const [experiment, setExperiment] = useState("");
  const [decision, setDecision] = useState<"keep" | "reject" | "inconclusive">(
    "inconclusive",
  );
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);
  const eligible = experiments.filter(
    (e) =>
      e.status === "complete" &&
      improvement.experiments.some((link) => link.id === e.id),
  );
  return (
    <Card title="Record the improvement decision">
      <p>
        Review results, regressions, uncertainty and calibration before
        deciding. This records your conclusion about the captured change.
      </p>
      <div className="stack">
        <SelectField
          label="Completed linked experiment"
          value={experiment}
          onChange={setExperiment}
          options={eligible.map((e) => ({
            id: e.id,
            label: `${e.split} · ${e.id}`,
          }))}
        />
        <div className="row">
          <Choice
            label="Improvement decision"
            value={decision}
            onChange={setDecision}
            options={["keep", "reject", "inconclusive"]}
          />
          <Field
            label="Decision reviewer"
            value={reviewer}
            onChange={setReviewer}
          />
        </div>
        <Field
          label="Decision reasoning"
          value={reason}
          onChange={setReason}
          multiline
        />
        <ActionButton
          action={async () => {
            if (!experiment || !reviewer.trim() || !reason.trim())
              throw new Error(
                "Select a completed linked experiment and record the reviewer and reason.",
              );
            await api.decideImprovement({
              id: improvement.id,
              experiment_id: experiment,
              decision,
              reviewer,
              reason,
            });
            setSaved(true);
          }}
        >
          Save improvement decision
        </ActionButton>
        {saved && (
          <p role="status">
            Decision recorded with the experiment evidence. Apply the change
            through your normal development workflow.
          </p>
        )}
      </div>
    </Card>
  );
}
export function ImprovementsView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const request = useWorkflow();
  const experiments = useQuery({
    queryKey: ["artifacts", "experiments"],
    queryFn: ({ signal }) => api.artifacts("experiments", signal),
  });
  const [selected, setSelected] = useState("");
  const [paths, setPaths] = useState({ baseline: "", candidate: "" });
  if (!request.data || !experiments.data)
    return <ResourceState error={request.error || experiments.error} />;
  const improvement = request.data.improvements.find((i) => i.id === selected);
  return (
    <>
      <Card title="Evidence to a measured change">
        <p>
          Capture a hypothesis, evaluate an exact source version, and keep an
          explicit history of human decisions.
        </p>
        <div className="workflow-library">
          {request.data.improvements.map((item) => (
            <button
              key={item.id}
              className={
                selected === item.id ? "selected-artifact" : "secondary"
              }
              onClick={() => {
                setSelected(item.id);
                setPaths({ baseline: "", candidate: "" });
              }}
            >
              {item.name}
              <span>
                {item.experiments.length} experiments ·{" "}
                {item.decisions.at(-1)?.decision || "awaiting evidence"}
              </span>
            </button>
          ))}
        </div>
        <button className="ghost" onClick={() => setSelected("")}>
          Capture another change
        </button>
      </Card>
      {!improvement ? (
        <ImprovementEditor
          improvements={request.data.improvements}
          onSaved={(id, baseline, candidate) => {
            setSelected(id);
            setPaths({ baseline, candidate });
          }}
        />
      ) : (
        <>
          <Card title={improvement.name}>
            <h3>Hypothesis</h3>
            <p>{improvement.hypothesis}</p>
            <h3>Expected behavior</h3>
            <p>{improvement.expected_behavior}</p>
            <Details title="Captured source patch">
              <JsonView value={improvement.patch} />
            </Details>
            <Details title="Exact runner identities and source snapshots">
              <JsonView
                value={{
                  baseline: improvement.baseline,
                  candidate: improvement.candidate,
                }}
              />
            </Details>
            <div className="pill-group">
              {improvement.trace_ids.map((id) => (
                <button
                  className="ghost"
                  key={id}
                  onClick={() => navigate({ view: "traces", id })}
                >
                  {id}
                </button>
              ))}
              {improvement.task_ids.map((id) => (
                <button
                  className="ghost"
                  key={id}
                  onClick={() => navigate({ view: "tasks", id })}
                >
                  Task {id}
                </button>
              ))}
            </div>
          </Card>
          <Card title="Linked experiments">
            {improvement.experiments.length ? (
              improvement.experiments.map((link) => {
                const e = experiments.data.find((e) => e.id === link.id);
                return (
                  <div className="item" key={link.id}>
                    <div className="item-head">
                      <h3>{e?.conclusion || link.id}</h3>
                      <Badge value={e?.status || "pending"} />
                    </div>
                    <p>
                      {e?.split || ""}
                      {e?.summary
                        ? ` · ${e.summary.improved.length} improved · ${e.summary.regressed.length} regressed`
                        : ""}
                    </p>
                    <button
                      className="ghost"
                      onClick={() =>
                        navigate({ view: "experiments", id: link.id })
                      }
                    >
                      Inspect paired results →
                    </button>
                  </div>
                );
              })
            ) : (
              <p className="muted">No experiments linked yet.</p>
            )}
          </Card>
          <ExperimentRun
            key={improvement.id}
            improvement={improvement}
            suites={request.data.suites || []}
            initialPaths={paths}
          />
          <ImprovementDecision
            key={`decision-${improvement.id}`}
            improvement={improvement}
            experiments={experiments.data}
          />
          {improvement.decisions.length > 0 && (
            <Card title="Decision history">
              {improvement.decisions.map((d, index) => (
                <div className="item" key={index}>
                  <Badge value={d.decision} />
                  <p>{d.reason}</p>
                  <small>
                    {d.reviewer} · {d.at}
                  </small>
                  <button
                    className="ghost"
                    onClick={() =>
                      navigate({ view: "experiments", id: d.experiment_id })
                    }
                  >
                    Review decision evidence →
                  </button>
                </div>
              ))}
            </Card>
          )}
        </>
      )}
    </>
  );
}
