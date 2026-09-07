import type { Trial } from "../contracts";
import { Badge, Details, JsonView, Table } from "../components/shared";
export function TrialEvidence({
  trial,
  showGrade = true,
}: {
  trial: Trial;
  showGrade?: boolean;
}) {
  const conversation = trial.runtime_evidence?.conversation;
  const environment = trial.runtime_evidence?.environment;
  return (
    <>
      <div className="pill-group">
        <Badge value={trial.execution.status} />
        {showGrade && <Badge value={trial.grade.status} />}
      </div>
      {conversation && (
        <section
          className="trial-transcript"
          aria-label="Conversation transcript"
        >
          <h3>Continuous conversation</h3>
          <p>
            {conversation.turns.length} attempted turns ·{" "}
            {conversation.stop_reason.replaceAll("_", " ")}
          </p>
          <small>
            Session {conversation.session_id || "unavailable"}. Completion is
            judged by the task verifier.
          </small>
          {conversation.turns.map((turn) => (
            <div className="conversation-turn" key={turn.index}>
              <div className="item-head">
                <h3>Turn {turn.index + 1}</h3>
                <Badge value={turn.status} />
              </div>
              <p className="conversation-user">
                <strong>User</strong>
                <br />
                {turn.user.message}
              </p>
              {turn.reply && (
                <>
                  <p className="conversation-reply">
                    <strong>Agent</strong>
                    <br />
                    {turn.reply.message}
                  </p>
                  {turn.reply.evidence.length > 0 && (
                    <Details title={`Tool evidence for turn ${turn.index + 1}`}>
                      <JsonView value={turn.reply.evidence} />
                    </Details>
                  )}
                </>
              )}
              {turn.error && <p className="error-text">{turn.error}</p>}
            </div>
          ))}
        </section>
      )}
      {environment && (
        <section aria-label="Environment lifecycle">
          <h3>Environment and authoritative observation</h3>
          <p>
            {environment.evidence_source.replaceAll("_", " ")} ·{" "}
            {environment.isolation.replaceAll("_", " ")}
          </p>
          <Table
            headings={["Phase", "Moment", "Status"]}
            rows={environment.phases.map((phase, index) => ({
              key: String(index),
              cells: [
                phase.phase,
                phase.moment || "—",
                <Badge key="state" value={phase.status} />,
              ],
            }))}
          />
          <div className="grid two">
            <Details title="Initial observed state">
              <JsonView value={environment.initial_state} />
            </Details>
            <Details title="Final observed state">
              <JsonView value={environment.final_state} />
            </Details>
          </div>
          <Details title="Environment commands, outputs and source identity">
            <JsonView value={environment} />
          </Details>
        </section>
      )}
      <Details title="Agent output">
        <JsonView value={trial.execution.output} />
      </Details>
      <Details title="Observed state and captured artifacts">
        <JsonView
          value={{ state: trial.state ?? {}, artifacts: trial.artifacts }}
        />
      </Details>
      {showGrade && (
        <>
          <Details title="Grader decisions">
            <JsonView value={trial.grade} />
          </Details>
          <Details title="Complete frozen trial record">
            <JsonView value={trial} />
          </Details>
        </>
      )}
    </>
  );
}
