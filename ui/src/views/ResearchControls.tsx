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
}: {
  resume?: Investigation;
  investigation?: string;
}) {
  const [backend, setBackend] = useState<Backend>("codex");
  const [model, setModel] = useState("");
  const [question, setQuestion] = useState(
    "Which failures and successful recoveries should we learn from?",
  );
  const [mode, setMode] = useState<"research" | "complete">("research");
  const [excludeFinal, setExcludeFinal] = useState(false);
  return (
    <Card
      title={
        investigation
          ? "Turn findings into draft tasks"
          : resume
            ? "Continue this investigation"
            : "Ask a research question"
      }
    >
      {!resume && !investigation && (
        <>
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
              ? "Explore adaptively and publish evidence for your question."
              : "Process every supplied record, save an outcome for each, and resolve failures before finishing."}
          </p>
          <label>
            <input
              type="checkbox"
              checked={excludeFinal}
              onChange={(event) => setExcludeFinal(event.target.checked)}
            />{" "}
            Exclude reserved final evaluation data
          </label>
        </>
      )}
      {resume?.session ? (
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
      )}
      <p className="muted">
        {investigation
          ? "The selected CLI creates drafts for review."
          : "Your native coding agent can query the full snapshot, write analysis code, and save reports and charts. Your CLI account and model limits apply."}
      </p>
      <ActionButton
        action={() =>
          investigation
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
              )
        }
      >
        {investigation
          ? "Design tasks"
          : resume
            ? "Resume investigation"
            : "Investigate"}
      </ActionButton>
    </Card>
  );
}
