import { useState } from "react";
import { api } from "../api";
import type { HarborExport } from "../workflow-contracts";
import {
  ActionButton,
  Card,
  Details,
  Field,
  JsonView,
} from "../components/shared";
export function HarborExportForm({ taskId }: { taskId: string }) {
  const [template, setTemplate] = useState("");
  const [agent, setAgent] = useState("");
  const [model, setModel] = useState("");
  const [environment, setEnvironment] = useState("docker");
  const [repetitions, setRepetitions] = useState("1");
  const [result, setResult] = useState<HarborExport | null>(null);
  return (
    <Details title="Export to Harbor">
      <Card title="Use a real Harbor environment">
        <p>
          Supply your Harbor task template with its environment and verifier.
          Export combines that template with this reviewed task and preserves
          the bundle identity.
        </p>
        <div className="stack">
          <Field
            label="Harbor template directory"
            value={template}
            onChange={setTemplate}
          />
          <div className="row">
            <Field label="Harbor agent" value={agent} onChange={setAgent} />
            <Field
              label="Harbor model (optional)"
              value={model}
              onChange={setModel}
            />
          </div>
          <div className="row">
            <Field
              label="Harbor environment type"
              value={environment}
              onChange={setEnvironment}
            />
            <Field
              label="Harbor repetitions"
              value={repetitions}
              onChange={setRepetitions}
              type="number"
              min={1}
            />
          </div>
          <ActionButton
            action={async () => {
              if (
                !template.trim() ||
                !agent.trim() ||
                !environment.trim() ||
                !repetitions.trim() ||
                !Number.isInteger(Number(repetitions)) ||
                Number(repetitions) < 1
              )
                throw new Error(
                  "Provide a template directory, agent, environment and positive repetition count.",
                );
              setResult(
                await api.exportHarbor(taskId, {
                  template_directory: template,
                  agent,
                  model,
                  environment_type: environment,
                  repetitions: Number(repetitions),
                }),
              );
            }}
          >
            Export reviewed Harbor task
          </ActionButton>
        </div>
        {result && (
          <div role="status">
            <p>
              Exported to <code>{result.bundle_directory}</code>
            </p>
            <p className="scope-note">{result.validation}</p>
            <Details title="Harbor launch arguments">
              <JsonView value={result.command} />
            </Details>
            <Details title="Export manifest and source identity">
              <JsonView value={result} />
            </Details>
          </div>
        )}
      </Card>
    </Details>
  );
}
