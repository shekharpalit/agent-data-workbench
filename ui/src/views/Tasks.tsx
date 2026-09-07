import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Route, Task, TaskSpec } from "../contracts";
import {
  ActionButton,
  Badge,
  Card,
  Details,
  Field,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";

export function TasksView({ navigate }: { navigate: (route: Route) => void }) {
  const request = useQuery({
    queryKey: ["artifacts", "tasks"],
    queryFn: ({ signal }) => api.artifacts("tasks", signal),
  });
  if (!request.data) return <ResourceState error={request.error} />;
  return (
    <Card title="Task library">
      <p className="muted">
        Inspect the behavior each test measures, audit its grader, then record a
        review decision.
      </p>
      <Table
        headings={["Task", "Behavior", "Fidelity", "Review", "Audit", ""]}
        rows={request.data.map((task) => ({
          key: task.id,
          cells: [
            task.spec.title,
            task.spec.behavior,
            task.spec.fidelity,
            <Badge key="review" value={task.review.status} />,
            <Badge
              key="audit"
              value={
                task.audit ? (task.audit.passed ? "pass" : "fail") : "pending"
              }
            />,
            <button
              key="open"
              className="ghost"
              onClick={() => navigate({ view: "tasks", id: task.id })}
            >
              Review →
            </button>,
          ],
        }))}
      />
      {!request.data.length && (
        <p className="muted">
          Design tasks from a completed investigation or import a specification
          through the CLI.
        </p>
      )}
    </Card>
  );
}
function TaskReview({ task }: { task: Task }) {
  const [note, setNote] = useState("");
  const [specification, setSpecification] = useState(
    JSON.stringify(task.spec, null, 2),
  );
  const [editNote, setEditNote] = useState("");
  return (
    <>
      <Card title="Review decision">
        <Field label="Review note" value={note} onChange={setNote} />
        <div className="row controls">
          <ActionButton
            action={() => api.reviewTask(task.id, "accepted", note)}
          >
            Accept task
          </ActionButton>
          <ActionButton
            className="danger"
            action={() => api.reviewTask(task.id, "rejected", note)}
          >
            Reject task
          </ActionButton>
        </div>
      </Card>
      <Details title="Edit the specification">
        <Card title="Edit task">
          <p className="muted">
            Saving retains the previous revision and resets both audit and
            review.
          </p>
          <Field
            label="Specification JSON"
            multiline
            value={specification}
            onChange={setSpecification}
          />
          <Field
            label="Reason for revision"
            value={editNote}
            onChange={setEditNote}
          />
          <ActionButton
            action={async () => {
              const value: unknown = JSON.parse(specification);
              if (
                typeof value !== "object" ||
                value === null ||
                Array.isArray(value)
              )
                throw new Error("Enter a task specification object.");
              return api.editTask(task.id, value as TaskSpec, editNote);
            }}
          >
            Save as draft
          </ActionButton>
        </Card>
      </Details>
    </>
  );
}
export function TaskDetail({
  id,
  navigate,
}: {
  id: string;
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["task", id],
    queryFn: ({ signal }) => api.artifact("tasks", id, signal),
  });
  if (!request.data) return <ResourceState error={request.error} />;
  const task = request.data,
    spec = task.spec;
  return (
    <>
      <button
        className="ghost breadcrumb"
        onClick={() => navigate({ view: "tasks" })}
      >
        ← Tasks & graders
      </button>
      <Card title={spec.title}>
        <div className="pill-group">
          <Badge value={task.review.status} />
          <Badge value={spec.fidelity} />
          <Badge value={spec.behavior} />
        </div>
        <p>{spec.purpose}</p>
        <div className="pill-group">
          {spec.trace_ids.map((traceId) => (
            <button
              className="ghost"
              key={traceId}
              onClick={() => navigate({ view: "traces", id: traceId })}
            >
              {traceId}
            </button>
          ))}
        </div>
      </Card>
      <div className="split">
        <Card title="Agent-visible input">
          <JsonView value={JSON.parse(spec.input_json) as unknown} />
          <small>
            The target receives this input. Grading rules stay in host-side
            artifacts.
          </small>
        </Card>
        <Card title="What the grader checks">
          {spec.criteria.map((criterion) => (
            <div className="item" key={criterion.id}>
              <h3>{criterion.description}</h3>
              <small>
                {criterion.source} · {criterion.artifact || criterion.kind}
              </small>
              <JsonView value={criterion.assertion || criterion.rubric} />
            </div>
          ))}
        </Card>
      </div>
      {spec.missing_context.length > 0 && (
        <Card title="Context needed before acceptance">
          {spec.missing_context.map((item, index) => (
            <p className="scope-note" key={index}>
              {item}
            </p>
          ))}
        </Card>
      )}
      <Card title="Assumptions">
        {spec.assumptions.length ? (
          spec.assumptions.map((item, index) => <p key={index}>{item}</p>)
        ) : (
          <p className="muted">No assumptions recorded.</p>
        )}
      </Card>
      <Card title="Grader sanity checks">
        <p className="muted">
          Correct answers, alternatives, mistakes, shortcuts and missing
          evidence. Semantic criteria require an explicitly configured judge
          through the CLI.
        </p>
        <ActionButton action={() => api.auditTask(id)}>
          Run deterministic audit
        </ActionButton>
        {task.audit && (
          <>
            <p>
              <Badge value={task.audit.passed ? "pass" : "fail"} />
            </p>
            <Table
              headings={["Example", "Kind", "Expected", "Actual"]}
              rows={task.audit.results.map((result) => ({
                key: result.name,
                cells: [
                  result.name,
                  result.kind,
                  result.expected,
                  <Badge key="status" value={result.actual} />,
                ],
              }))}
            />
            <Details title="Criterion evidence and decisions">
              <JsonView value={task.audit} />
            </Details>
          </>
        )}
        <Details title="Audit examples">
          <JsonView value={spec.verifier_examples} />
        </Details>
      </Card>
      <TaskReview key={`${id}-${JSON.stringify(spec)}`} task={task} />
    </>
  );
}
