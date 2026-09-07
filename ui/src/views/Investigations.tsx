import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Backend, Route } from "../contracts";
import {
  ActionButton,
  Badge,
  Card,
  Details,
  Field,
  JsonView,
  ProviderFields,
  ResourceState,
  Table,
} from "../components/shared";

function ResearchControls({
  resume,
  investigation,
}: {
  resume?: string;
  investigation?: string;
}) {
  const [backend, setBackend] = useState<Backend>("codex");
  const [model, setModel] = useState("");
  const [question, setQuestion] = useState(
    "Which failures and successful recoveries should we learn from?",
  );
  const [steps, setSteps] = useState("6");
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
        <Field
          label="What do you want to understand?"
          multiline
          value={question}
          onChange={setQuestion}
        />
      )}
      <ProviderFields
        backend={backend}
        model={model}
        onBackend={setBackend}
        onModel={setModel}
      />
      {!investigation && (
        <Field
          label="Maximum model calls (1–12)"
          type="number"
          min={1}
          max={12}
          value={steps}
          onChange={setSteps}
        />
      )}
      <p className="muted">
        Selected traces and reviewed context go through your chosen CLI. Its
        account limits apply. Generated tasks start as drafts.
      </p>
      <ActionButton
        action={() =>
          investigation
            ? api.designTasks(investigation, backend, model)
            : api.investigate({
                question,
                ...(resume ? { resume } : {}),
                backend,
                model,
                steps: Number(steps),
              })
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
export function InvestigationsView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["artifacts", "investigations"],
    queryFn: ({ signal }) => api.artifacts("investigations", signal),
  });
  return (
    <>
      <ResearchControls />
      {request.data ? (
        <Card title="Research history">
          {[...request.data]
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
            .map((item) => (
              <div className="item" key={item.id}>
                <div className="item-head">
                  <h3>{item.question}</h3>
                  <Badge value={item.status} />
                </div>
                <p className="muted">
                  {item.steps.length} completed steps ·{" "}
                  {item.visited_ids.length} trace IDs visited
                </p>
                <button
                  className="ghost"
                  onClick={() =>
                    navigate({ view: "investigations", id: item.id })
                  }
                >
                  Open investigation →
                </button>
              </div>
            ))}
          {!request.data.length && (
            <p className="muted">
              Start with a question. The investigator can search, sample,
              inspect and aggregate traces.
            </p>
          )}
        </Card>
      ) : (
        <ResourceState error={request.error} />
      )}
    </>
  );
}
export function InvestigationDetail({
  id,
  navigate,
}: {
  id: string;
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["investigation", id],
    queryFn: ({ signal }) => api.artifact("investigations", id, signal),
  });
  if (!request.data) return <ResourceState error={request.error} />;
  const item = request.data,
    result = item.result;
  return (
    <>
      <button
        className="ghost breadcrumb"
        onClick={() => navigate({ view: "investigations" })}
      >
        ← Investigations
      </button>
      <Card title={item.question}>
        <Badge value={item.status} />
        <p className="muted">
          {item.visited_ids.length} / {item.source.total} eligible trace IDs
          visited. A preview is not a complete trace review.
        </p>
      </Card>
      {result ? (
        <>
          <Card title="Research findings">
            <p>{result.analysis.summary}</p>
          </Card>
          {result.analysis.findings.map((finding) => (
            <Card key={finding.id} title={finding.title}>
              <div className="pill-group">
                <Badge value={finding.category} />
                <Badge value={finding.confidence} />
              </div>
              <p>{finding.explanation}</p>
              <p>Suggested action: {finding.recommendation}</p>
              {finding.evidence.map((evidence, index) => (
                <blockquote key={index}>
                  <button
                    className="ghost"
                    onClick={() =>
                      navigate({ view: "traces", id: evidence.trace_id })
                    }
                  >
                    {evidence.trace_id} · {evidence.pointer}
                  </button>
                  <p>{evidence.quote}</p>
                </blockquote>
              ))}
            </Card>
          ))}
          {!!result.signals.length && (
            <Card title="Signals">
              <Table
                headings={[
                  "Finding",
                  "Kind",
                  "Impact",
                  "Evidence for priority",
                ]}
                rows={result.signals.map((signal, i) => ({
                  key: String(i),
                  cells: [
                    signal.finding_id,
                    signal.kind,
                    signal.impact,
                    signal.impact_reason,
                  ],
                }))}
              />
            </Card>
          )}
          {result.proposals.map((proposal) => (
            <Card key={proposal.id} title={proposal.title}>
              <Badge value={proposal.kind} />
              <p>{proposal.hypothesis}</p>
              <p>Experiment: {proposal.evaluation_plan}</p>
              <Details title="Inspect proposed edits">
                <JsonView value={proposal.edits} />
              </Details>
            </Card>
          ))}
          <Card title="Open questions and limits">
            {[...result.open_questions, ...result.analysis.limitations].map(
              (text, index) => (
                <p key={index}>{text}</p>
              ),
            )}
          </Card>
          <ResearchControls investigation={id} />
        </>
      ) : (
        <>
          <p className="scope-note">
            {item.error ||
              "Completed work is saved. Continue with an explicit call budget."}
          </p>
          <ResearchControls resume={id} />
        </>
      )}
      <Card title="Investigation journal">
        {item.steps.map((step, i) => (
          <Details
            key={i}
            title={`${i + 1}. ${step.decision.action} — ${step.decision.note}`}
          >
            <JsonView value={step.observation} />
          </Details>
        ))}
      </Card>
    </>
  );
}
