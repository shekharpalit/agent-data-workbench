import { useState } from "react";
import { api } from "../api";
import type { Route } from "../contracts";
import type { HarborAgentConfig } from "../workflow-contracts";
import { RuntimeStatus } from "../components/RuntimeStatus";
import { ActionButton, Card, Details, Field } from "../components/shared";

function parseKwargs(text: string): HarborAgentConfig["agent_kwargs"] {
  const value: unknown = JSON.parse(text);
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.values(value).some(
      (item) => !["string", "number", "boolean"].includes(typeof item),
    )
  )
    throw new Error(
      "Agent options must be a JSON object with string, number or boolean values.",
    );
  return value as HarborAgentConfig["agent_kwargs"];
}
export function HarborComparisonForm({
  taskId,
  navigate,
}: {
  taskId: string;
  navigate: (route: Route) => void;
}) {
  const [template, setTemplate] = useState("");
  const [baseline, setBaseline] = useState({ agent: "", model: "" });
  const [candidate, setCandidate] = useState({ agent: "", model: "" });
  const [baselineKwargs, setBaselineKwargs] = useState("{}");
  const [candidateKwargs, setCandidateKwargs] = useState("{}");
  const [environment, setEnvironment] = useState("docker");
  const [repeats, setRepeats] = useState("1");
  const [reward, setReward] = useState("reward");
  const [threshold, setThreshold] = useState("1");
  const [started, setStarted] = useState(false);
  return (
    <Card title="Run a Harbor comparison">
      <p>
        Run baseline and candidate agents against this accepted task, using the
        same frozen environment and verifier. Results and available trajectories
        return to this workbench automatically.
      </p>
      <Details title="Check Harbor runtime setup">
        <RuntimeStatus tools={["harbor", "docker"]} />
      </Details>
      <Field
        label="Harbor task template directory"
        value={template}
        onChange={setTemplate}
        placeholder="/path/to/task-template"
      />
      <p className="muted">
        Use an existing Harbor template containing task.toml, an environment,
        and tests/test.sh. The verifier must check the intended behavior of this
        reviewed task.
      </p>
      <div className="grid two">
        {(["baseline", "candidate"] as const).map((variant) => {
          const value = variant === "baseline" ? baseline : candidate;
          const change = variant === "baseline" ? setBaseline : setCandidate;
          return (
            <div key={variant}>
              <h3>{variant === "baseline" ? "Baseline" : "Candidate"}</h3>
              <Field
                label={`${variant} agent`}
                value={value.agent}
                onChange={(agent) => change({ ...value, agent })}
                placeholder="codex, claude-code, or package:AgentClass"
              />
              <Field
                label={`${variant} model (optional)`}
                value={value.model}
                onChange={(model) => change({ ...value, model })}
              />
              <Details title={`${variant} agent options`}>
                <Field
                  label={`${variant} kwargs (JSON)`}
                  multiline
                  value={
                    variant === "baseline" ? baselineKwargs : candidateKwargs
                  }
                  onChange={
                    variant === "baseline"
                      ? setBaselineKwargs
                      : setCandidateKwargs
                  }
                />
              </Details>
            </div>
          );
        })}
      </div>
      <div className="row">
        <Field
          label="Harbor environment"
          value={environment}
          onChange={setEnvironment}
        />
        <Field
          label="Paired repetitions"
          type="number"
          min={1}
          value={repeats}
          onChange={setRepeats}
        />
        <Field
          label="Verifier reward key"
          value={reward}
          onChange={setReward}
        />
        <Field
          label="Pass when reward is at least"
          type="number"
          value={threshold}
          onChange={setThreshold}
        />
      </div>
      <p className="scope-note">
        Missing rewards and execution errors are invalid outcomes. This
        exploratory comparison uses the Harbor verifier; the workbench task
        audit does not automatically validate that verifier. Harbor agents use
        their own credential configuration inside their execution environment.
      </p>
      <ActionButton
        action={async () => {
          if (
            !template.trim() ||
            !baseline.agent.trim() ||
            !candidate.agent.trim() ||
            !reward.trim() ||
            !environment.trim()
          )
            throw new Error(
              "Provide a template, both agents, an environment and reward key.",
            );
          if (
            !repeats.trim() ||
            !Number.isInteger(Number(repeats)) ||
            Number(repeats) < 1 ||
            !threshold.trim() ||
            !Number.isFinite(Number(threshold))
          )
            throw new Error(
              "Use a positive repetition count and a numeric pass threshold.",
            );
          await api.compareHarbor(taskId, {
            template_directory: template,
            baseline: {
              ...baseline,
              agent_kwargs: parseKwargs(baselineKwargs),
            },
            candidate: {
              ...candidate,
              agent_kwargs: parseKwargs(candidateKwargs),
            },
            environment_type: environment,
            repetitions: Number(repeats),
            reward_key: reward,
            pass_threshold: Number(threshold),
            timeout: null,
          });
          setStarted(true);
        }}
      >
        Run baseline & candidate
      </ActionButton>
      {started && (
        <p role="status">
          Comparison submitted. Open the completed result from the job bar, or
          inspect saved trials while it runs.
        </p>
      )}
      <button
        className="ghost"
        onClick={() => navigate({ view: "experiments" })}
      >
        View experiments →
      </button>
    </Card>
  );
}
