import { RuntimeStatus } from "../components/RuntimeStatus";
import { useState } from "react";
import { api } from "../api";
import type { Backend, Investigation } from "../contracts";
import {
  ActionButton,
  Card,
  Choice,
  Field,
  ProviderFields,
} from "../components/shared";

export function ResearchControls({
  resume,
  investigation,
  onCreated,
}: {
  resume?: Investigation;
  investigation?: string;
  onCreated?: (item: Investigation) => void;
}) {
  const [researcher, setResearcher] = useState<"manual" | "agent">("manual");
  const [backend, setBackend] = useState<Backend>("codex");
  const [model, setModel] = useState("");
  const [question, setQuestion] = useState(
    "Which failures and successful recoveries should we learn from?",
  );
  const [mode, setMode] = useState<"research" | "complete">("research");
  const [excludeFinal, setExcludeFinal] = useState(false);
  const manual = !resume && !investigation && researcher === "manual";
  return (
    <Card
      title={
        investigation
          ? "Turn findings into draft tasks"
          : resume
            ? resume.session
              ? "Continue with your agent"
              : "Bring in an agent"
            : "Start research"
      }
    >
      {!resume && !investigation && (
        <div className="stack">
          <div
            className="row research-choice"
            role="group"
            aria-label="Who will research?"
          >
            <button
              className={manual ? "" : "secondary"}
              aria-pressed={manual}
              onClick={() => setResearcher("manual")}
            >
              Research myself
            </button>
            <button
              className={manual ? "secondary" : ""}
              aria-pressed={!manual}
              onClick={() => setResearcher("agent")}
            >
              Use an agent
            </button>
          </div>
          <Field
            label="What do you want to understand?"
            multiline
            value={question}
            onChange={setQuestion}
          />
          <Choice
            label="Analysis mode"
            value={mode}
            options={["research", "complete"]}
            onChange={setMode}
          />
          <p className="muted">
            {mode === "research"
              ? "Explore the dataset and publish evidence for your question."
              : "Save an outcome for every supplied record and resolve failures before finishing."}
          </p>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={excludeFinal}
              onChange={(event) => setExcludeFinal(event.target.checked)}
            />
            Exclude reserved final evaluation data
          </label>
        </div>
      )}
      {!manual &&
        (resume?.session ? (
          <p>
            Resume {resume.session.backend} ·{" "}
            {resume.session.model || "CLI default model"}. The native session
            retains its context.
          </p>
        ) : (
          <ProviderFields
            backend={backend}
            model={model}
            onBackend={setBackend}
            onModel={setModel}
          />
        ))}
      <p className="muted">
        {manual
          ? "Open a workspace to inspect records, save notes and outcomes, and publish your findings and charts. No model is called."
          : investigation
            ? "The selected CLI creates drafts for review."
            : "Your native coding agent can query the full snapshot, write analysis code, and save reports and charts. Your CLI account and model limits apply."}
      </p>
      {!manual && (
        <RuntimeStatus tools={[resume?.session?.backend || backend]} />
      )}
      <ActionButton
        action={async () => {
          if (manual) {
            const created = await api.createResearch({
              question,
              mode,
              exclude_final: excludeFinal,
            });
            onCreated?.(created);
            return;
          }
          return investigation
            ? api.designTasks(investigation, backend, model)
            : api.investigate(
                resume
                  ? {
                      resume: resume.id,
                      ...(resume.session ? {} : { backend, model }),
                    }
                  : {
                      question,
                      backend,
                      model,
                      mode,
                      exclude_final: excludeFinal,
                    },
              );
        }}
      >
        {manual
          ? "Start manual research"
          : investigation
            ? "Design tasks"
            : resume
              ? resume.session
                ? "Resume investigation"
                : "Start agent session"
              : "Investigate"}
      </ActionButton>
    </Card>
  );
}
