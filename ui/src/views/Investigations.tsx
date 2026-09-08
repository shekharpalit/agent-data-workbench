import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Route } from "../contracts";
import {
  ActionButton,
  Badge,
  Card,
  Details,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";

import { useState } from "react";
import { ManualResearchEditor } from "./ManualResearchEditor";
import { ResearchSnapshot, SnapshotCitation } from "./ResearchSnapshot";
import { ResearchControls } from "./ResearchControls";
import { ResearchFiles, ResearchProgress } from "./ResearchOutputs";

export function InvestigationsView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["artifacts", "investigations"],
    queryFn: ({ signal }) => api.artifacts("investigations", signal),
    refetchInterval: 2000,
  });
  return (
    <>
      <ResearchControls
        onCreated={(item) => navigate({ view: "investigations", id: item.id })}
      />
      {request.data ? (
        <Card title="Research history">
          {[...request.data]
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
            .map((item) => (
              <div className="item" key={item.id}>
                <div className="item-head">
                  <h3>
                    {item.session
                      ? `${item.session.backend} research`
                      : "Manual research"}
                  </h3>
                  <Badge value={item.status} />
                </div>
                <p className="muted">
                  {new Date(item.created_at).toLocaleString()}
                </p>
                <Details title="Research question">
                  <p>{item.question}</p>
                </Details>
                <p className="muted">
                  {item.mode === "complete" ? "Complete pass" : "Research"} ·{" "}
                  {item.coverage.completed} / {item.coverage.total} records
                  processed · {item.coverage.failed} failed
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
              Start with a question. Research the dataset yourself or ask an
              agent to help.
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
  const [agentControls, setAgentControls] = useState(false);
  const request = useQuery({
    queryKey: ["investigation", id],
    queryFn: ({ signal }) => api.artifact("investigations", id, signal),
    refetchInterval: (query) =>
      query.state.data?.status !== "complete" || query.state.data?.active
        ? 2000
        : false,
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
      <Card title="Research session">
        <Badge value={item.status} />
        {item.session && (
          <p className="muted">
            {item.session.backend} · {item.session.model || "CLI default model"}
            {item.session.reasoning_effort
              ? ` · ${item.session.reasoning_effort} effort`
              : ""}
          </p>
        )}
        <Details title="Research question">
          <p>{item.question}</p>
        </Details>
        <p className="muted">
          {item.coverage.completed.toLocaleString()} /{" "}
          {item.coverage.total.toLocaleString()} records processed ·{" "}
          {item.coverage.failed} failed · {item.coverage.pending} pending
        </p>
        <p className="muted">
          {item.coverage.retrieved} records returned through SDK reads or
          processing. Direct file reads are not counted; retrieval does not
          establish semantic review.
        </p>
        {item.session && (
          <Details
            title={`${item.session.backend} · ${(item.attempts || []).length} session attempts`}
          >
            <JsonView
              value={{ session: item.session, attempts: item.attempts }}
            />
          </Details>
        )}
        {item.active && (
          <ActionButton
            className="secondary"
            action={() => api.pauseResearch(id)}
          >
            Pause session
          </ActionButton>
        )}
      </Card>
      {item.error && <p className="scope-note">{item.error}</p>}
      {item.status !== "complete" &&
        !item.active &&
        (item.protocol_version === "0.4" ? (
          <>
            <button
              className="ghost breadcrumb"
              aria-expanded={agentControls}
              onClick={() => setAgentControls(!agentControls)}
            >
              {agentControls
                ? "Hide agent controls"
                : item.session
                  ? "Continue with an agent"
                  : "Bring in an agent"}
            </button>
            {agentControls && <ResearchControls resume={item} />}
          </>
        ) : (
          <p className="scope-note">
            This investigation uses the earlier protocol. Start a new
            investigation to use native sessions.
          </p>
        ))}
      {result && (
        <Card title="Research findings">
          <p>{result.analysis.summary}</p>
        </Card>
      )}
      <ResearchFiles item={item} />
      {result ? (
        <>
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
                  {item.protocol_version === "0.4" ? (
                    <SnapshotCitation item={item} evidence={evidence} />
                  ) : (
                    <button
                      className="ghost"
                      onClick={() =>
                        navigate({ view: "traces", id: evidence.trace_id })
                      }
                    >
                      {evidence.trace_id} · {evidence.pointer}
                    </button>
                  )}
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
          {!!result.analysis.cases.length && (
            <Card title="Evaluation blueprints">
              <p className="muted">
                Proposed cases from this research. Review their environment,
                inputs and verifier before creating or running tasks.
              </p>
              {result.analysis.cases.map((candidate) => (
                <Details key={candidate.id} title={candidate.title}>
                  <JsonView value={candidate} />
                </Details>
              ))}
            </Card>
          )}
          <Card title="Open questions and limits">
            {[...result.open_questions, ...result.analysis.limitations].map(
              (text, index) => (
                <p key={index}>{text}</p>
              ),
            )}
          </Card>
          <Details title="Use an agent to design tasks">
            <ResearchControls investigation={id} />
          </Details>
        </>
      ) : null}
      {item.protocol_version === "0.4" && (
        <>
          <ResearchSnapshot key={id} item={item} />
          <ManualResearchEditor key={id} item={item} />
        </>
      )}
      {item.protocol_version === "0.4" ? (
        <ResearchProgress key={id} item={item} />
      ) : (
        <Card title="Investigation journal">
          <JsonView value={item.journal} />
        </Card>
      )}
    </>
  );
}
