import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Route, SearchQuery } from "../contracts";
import {
  Bars,
  Card,
  Details,
  Field,
  JsonView,
  ResourceState,
  Table,
  submit,
} from "../components/shared";

export function DatasetView({
  query,
  onMembers,
  navigate,
}: {
  query: SearchQuery;
  onMembers: (ids: string[]) => void;
  navigate: (route: Route) => void;
}) {
  const [pointer, setPointer] = useState("/resolved");
  const [active, setActive] = useState("/resolved");
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const request = useQuery({
    queryKey: ["dataset-profile", query, active],
    queryFn: ({ signal }) => api.datasetProfile(query, active, signal),
  });
  const data = request.data;
  const groups =
    data?.groups.filter((group) =>
      `${group.label} ${group.strata.join(" ")}`
        .toLowerCase()
        .includes(filter.toLowerCase()),
    ) || [];
  const page = groups.slice(offset, offset + 20);
  return (
    <>
      <Card title="What happened across these runs?">
        <p>
          Compare recorded outcomes and find tasks with repeated attempts. Click
          a task to inspect its original traces.
        </p>
        <form className="row" onSubmit={submit(() => setActive(pointer))}>
          <Field
            label="Binary outcome field"
            value={pointer}
            onChange={setPointer}
            placeholder="/resolved"
          />
          <button>Update outcomes</button>
        </form>
        <p className="muted">
          True or 1 means passed; false or 0 means failed. Other values remain
          unknown. These are dataset labels, not a new evaluation.
        </p>
      </Card>
      {data ? (
        <>
          <div className="grid two">
            <Card title="Recorded outcomes">
              <p>{data.eligible} matching runs</p>
              <Bars
                values={data.outcomes}
                total={data.eligible}
                colors={{
                  Passed: "#36785b",
                  Failed: "#bf654b",
                  Unknown: "#8e98a0",
                }}
              />
              <p className="muted">
                Use the task table below to inspect individual outcomes.
              </p>
            </Card>
            <Card title="Repeated attempts">
              <div className="metric">
                {data.groups.filter((group) => group.count > 1).length}
              </div>
              <p>
                tasks have multiple runs · {data.group_count} source groups
                total
              </p>
              <p>
                Repeated runs from the same task are related evidence. They are
                not independent tasks when estimating improvement.
              </p>
              <button
                className="secondary"
                onClick={() => navigate({ view: "clusters" })}
              >
                Find shared language →
              </button>
            </Card>
          </div>
          <Card title="Attempts by task">
            <p>
              Each bar counts actual imported runs for the same source group.
              Color shows the recorded outcome; bar length is the run count.
            </p>
            <div className="graph-legend">
              <span>
                <i className="outcome-pass" />
                Passed
              </span>
              <span>
                <i className="outcome-fail" />
                Failed
              </span>
              <span>
                <i className="outcome-unknown" />
                Unknown
              </span>
            </div>
            <Field
              label="Find a task or repository"
              value={filter}
              onChange={(value) => {
                setFilter(value);
                setOffset(0);
              }}
            />
            <div
              className="attempt-chart"
              role="group"
              aria-label="Recorded attempts by task"
            >
              {page.map((group) => (
                <button
                  key={group.id}
                  className="attempt-row"
                  onClick={() => onMembers(group.trace_ids)}
                  aria-label={`${group.label}: ${group.count} runs, ${group.outcomes.Passed} passed, ${group.outcomes.Failed} failed, ${group.outcomes.Unknown} unknown`}
                >
                  <span className="attempt-label">{group.label}</span>
                  <span className="attempt-track">
                    <span
                      className="attempt-bar"
                      style={{
                        width: `${(group.count / groups.reduce((maximum, g) => Math.max(maximum, g.count), 1)) * 100}%`,
                      }}
                    >
                      {(["Passed", "Failed", "Unknown"] as const).map(
                        (label) => (
                          <span
                            key={label}
                            className={`outcome-${label === "Passed" ? "pass" : label === "Failed" ? "fail" : "unknown"}`}
                            style={{
                              width: `${(group.outcomes[label] / group.count) * 100}%`,
                            }}
                          />
                        ),
                      )}
                    </span>
                  </span>
                  <span>{group.count}</span>
                </button>
              ))}
            </div>
            <Table
              headings={[
                "Task / source group",
                "Repository / category",
                "Passed",
                "Failed",
                "Unknown",
                "Traces",
              ]}
              rows={page.map((group) => ({
                key: group.id,
                cells: [
                  group.label,
                  group.strata.join(", "),
                  group.outcomes.Passed,
                  group.outcomes.Failed,
                  group.outcomes.Unknown,
                  <button
                    key="open"
                    className="ghost"
                    onClick={() => onMembers(group.trace_ids)}
                  >
                    Inspect {group.count} runs →
                  </button>,
                ],
              }))}
            />
            <div className="row">
              <small>
                {groups.length ? offset + 1 : 0}–{offset + page.length} of{" "}
                {groups.length} groups
              </small>
              <button
                className="secondary"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Previous tasks
              </button>
              <button
                className="secondary"
                disabled={offset + 20 >= groups.length}
                onClick={() => setOffset(offset + 20)}
              >
                Next tasks
              </button>
            </div>
            <Details title="Complete dataset counts and group membership">
              <JsonView value={data} />
            </Details>
            <p className="scope-note">{data.scope}</p>
            {!data.eligible && (
              <button onClick={() => navigate({ view: "imports" })}>
                Import traces →
              </button>
            )}
          </Card>
        </>
      ) : (
        <ResourceState error={request.error} />
      )}
    </>
  );
}
