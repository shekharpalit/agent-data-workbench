import { useState } from "react";
import { Conversation } from "../components/traces/Conversation";
import { traceTitle } from "../components/traces/presentation";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { FieldFilter, Route, SearchQuery } from "../contracts";
import { filterValue, initialSearch } from "../state";
import {
  Bars,
  Card,
  Choice,
  Details,
  Field,
  JsonView,
  ResourceState,
  Table,
  submit,
} from "../components/shared";

type DraftFilter = {
  pointer: string;
  operator: FieldFilter["operator"];
  value: string;
};
type SearchDraft = Omit<SearchQuery, "filters"> & { filters: DraftFilter[] };
function draftQuery(query: SearchQuery): SearchDraft {
  return {
    ...query,
    filters: query.filters.map((filter) => ({
      pointer: filter.pointer,
      operator: filter.operator,
      value: displayValue(filter.operator, filter.value_json),
    })),
  };
}
export function SearchForm({
  query,
  onApply,
}: {
  query: SearchQuery;
  onApply: (query: SearchQuery) => void;
}) {
  const [draft, setDraft] = useState(() => draftQuery(query));
  const [error, setError] = useState("");
  function updateFilter(index: number, patch: Partial<DraftFilter>) {
    setDraft((value) => ({
      ...value,
      filters: value.filters.map((filter, i) =>
        i === index ? { ...filter, ...patch } : filter,
      ),
    }));
  }
  function apply() {
    try {
      onApply({
        ...draft,
        offset: 0,
        filters: draft.filters.map((filter) => ({
          pointer: filter.pointer,
          operator: filter.operator,
          value_json: filterValue(filter.operator, filter.value),
        })),
      });
      setError("");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Invalid filter");
    }
  }
  return (
    <form onSubmit={submit(apply)}>
      <div className="row">
        <Field
          label="Search trace content"
          value={draft.text}
          onChange={(text) => setDraft({ ...draft, text })}
          placeholder="Errors, user corrections, tool results…"
        />
        <Field
          label="Agent group"
          value={draft.stratum}
          onChange={(stratum) => setDraft({ ...draft, stratum })}
          placeholder="All groups"
        />
      </div>
      {draft.filters.map((filter, index) => (
        <div className="filter-row" key={index}>
          <Field
            label={`Field ${index + 1}`}
            value={filter.pointer}
            onChange={(pointer) => updateFilter(index, { pointer })}
            placeholder="/tool_result/status"
          />
          <Choice
            label={`Condition ${index + 1}`}
            value={filter.operator}
            options={["equals", "contains", "gte", "lte", "exists", "missing"]}
            onChange={(operator) => updateFilter(index, { operator })}
          />
          {!["exists", "missing"].includes(filter.operator) && (
            <Field
              label={`Value ${index + 1}`}
              value={filter.value}
              onChange={(value) => updateFilter(index, { value })}
            />
          )}
          <button
            type="button"
            className="ghost"
            aria-label={`Remove filter ${index + 1}`}
            onClick={() =>
              setDraft({
                ...draft,
                filters: draft.filters.filter((_, i) => i !== index),
              })
            }
          >
            Remove
          </button>
        </div>
      ))}
      <div className="row controls">
        <button
          type="button"
          className="secondary"
          disabled={draft.filters.length >= 8}
          onClick={() =>
            setDraft({
              ...draft,
              filters: [
                ...draft.filters,
                {
                  pointer: "/tool_result/status",
                  operator: "equals",
                  value: "declined",
                },
              ],
            })
          }
        >
          + Add field filter
        </button>
        <span className="muted">
          All conditions must match. JSON numbers and booleans keep their types.
        </span>
      </div>
      <div className="row">
        <Field
          label="Sort by ID or JSON pointer"
          value={draft.sort}
          onChange={(sort) => setDraft({ ...draft, sort })}
        />
        <Choice
          label="Direction"
          value={draft.direction}
          options={["asc", "desc"]}
          onChange={(direction) => setDraft({ ...draft, direction })}
        />
        <Choice
          label="Rows per page"
          value={String(draft.limit)}
          options={["20", "50", "100"]}
          onChange={(limit) => setDraft({ ...draft, limit: Number(limit) })}
        />
        <button type="submit">Search</button>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            setDraft(draftQuery(initialSearch));
            setError("");
            onApply(initialSearch);
          }}
        >
          Reset
        </button>
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </form>
  );
}
function displayValue(
  operator: FieldFilter["operator"],
  value: string,
): string {
  if (operator !== "contains") return value;
  try {
    const parsed: unknown = JSON.parse(value);
    return typeof parsed === "string" ? parsed : value;
  } catch {
    return value;
  }
}

export function SearchView({
  query,
  onQuery,
  navigate,
}: {
  query: SearchQuery;
  onQuery: (query: SearchQuery) => void;
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["search", query],
    queryFn: ({ signal }) => api.search(query, signal),
  });
  const [filterError, setFilterError] = useState("");
  const [pointer, setPointer] = useState("/tool_result/status");
  const [activePointer, setActivePointer] = useState("/tool_result/status");
  const distribution = useQuery({
    queryKey: ["distribution", query, activePointer],
    queryFn: ({ signal }) => api.distribution(query, activePointer, signal),
  });
  const data = request.data;
  return (
    <>
      <Card title="Search your trace corpus">
        <button
          className="secondary"
          onClick={() => navigate({ view: "imports" })}
        >
          Import data →
        </button>
        <SearchForm
          key={JSON.stringify(query)}
          query={query}
          onApply={onQuery}
        />
        {query.trace_ids && (
          <p className="scope-note">
            Showing members of the selected trace group.{" "}
            <button
              className="ghost"
              onClick={() => onQuery({ ...query, trace_ids: null, offset: 0 })}
            >
              Clear membership filter
            </button>
          </p>
        )}
      </Card>
      {data ? (
        <Card title={`${data.eligible} matching traces`}>
          <div className="row toolbar">
            <small>
              Stable sorting · missing values last · {data.selected} shown
            </small>
            <button
              className="secondary"
              onClick={() => navigate({ view: "clusters" })}
            >
              Cluster these results →
            </button>
          </div>
          <Table
            headings={["Trace", "Group", "Input / request", "Evidence"]}
            rows={data.records.map((trace) => ({
              key: trace.trace_id,
              cells: [
                traceTitle(trace),
                trace.stratum,
                trace.data.input !== undefined ||
                trace.data.request !== undefined ? (
                  <Details title="Read input / request" key="input">
                    <JsonView
                      value={
                        trace.data.input !== undefined
                          ? trace.data.input
                          : trace.data.request
                      }
                    />
                  </Details>
                ) : (
                  "Inspect trace"
                ),
                <div className="row" key="actions">
                  <button
                    className="ghost"
                    onClick={() =>
                      navigate({ view: "traces", id: trace.trace_id })
                    }
                  >
                    Inspect
                  </button>
                  <button
                    className="ghost"
                    onClick={() =>
                      navigate({ view: "graph", id: trace.trace_id })
                    }
                  >
                    Graph
                  </button>
                </div>,
              ],
            }))}
          />
          <div className="row controls">
            <small>
              {data.eligible ? query.offset + 1 : 0}–
              {query.offset + data.selected} of {data.eligible}
            </small>
            <button
              className="secondary"
              disabled={!query.offset}
              onClick={() =>
                onQuery({
                  ...query,
                  offset: Math.max(0, query.offset - query.limit),
                })
              }
            >
              Previous
            </button>
            <button
              className="secondary"
              disabled={query.offset + query.limit >= data.eligible}
              onClick={() =>
                onQuery({ ...query, offset: query.offset + query.limit })
              }
            >
              Next
            </button>
          </div>
          {data.eligible === 0 && (
            <p className="muted">
              No matching traces. Try removing a field filter.
            </p>
          )}
        </Card>
      ) : (
        <ResourceState error={request.error} />
      )}
      <Card title="Distribution across all matching traces">
        {filterError && (
          <p role="alert" className="error-text">
            {filterError}
          </p>
        )}
        <form
          className="row"
          onSubmit={submit(() => setActivePointer(pointer))}
        >
          <label className="field">
            <span>Fields found in these results</span>
            <select
              value=""
              onChange={(event) => {
                setPointer(event.target.value);
                setActivePointer(event.target.value);
              }}
            >
              <option value="">Choose a field…</option>
              {Object.keys(data?.records[0]?.data || {})
                .filter((key) => {
                  const value = data?.records[0]?.data[key];
                  return value === null || typeof value !== "object";
                })
                .map((key) => {
                  const path =
                    "/" + key.replaceAll("~", "~0").replaceAll("/", "~1");
                  return (
                    <option key={path} value={path}>
                      {path}
                    </option>
                  );
                })}
            </select>
          </label>
          <Field
            label="Field to aggregate"
            value={pointer}
            onChange={setPointer}
          />
          <button>Calculate</button>
        </form>
        {distribution.data ? (
          <>
            <Bars
              values={distribution.data.counts}
              total={distribution.data.eligible}
              onSelect={(value) => {
                if (query.filters.length >= 8) {
                  setFilterError(
                    "Remove a filter before adding another condition.",
                  );
                  return;
                }
                setFilterError("");
                onQuery({
                  ...query,
                  offset: 0,
                  filters: [
                    ...query.filters,
                    {
                      pointer: activePointer,
                      operator: "equals",
                      value_json: JSON.stringify(value),
                    },
                  ],
                });
              }}
            />
            <small>
              {distribution.data.eligible} matched ·{" "}
              {distribution.data.missing_or_non_scalar} missing/non-scalar ·
              mean {distribution.data.mean ?? "unavailable"}
            </small>
            <Details title="Exact aggregate data">
              <JsonView value={distribution.data} />
            </Details>
          </>
        ) : (
          <ResourceState error={distribution.error} />
        )}
      </Card>
    </>
  );
}
export function TraceDetail({
  id,
  navigate,
}: {
  id: string;
  navigate: (route: Route) => void;
}) {
  const request = useQuery({
    queryKey: ["trace", id],
    queryFn: ({ signal }) => api.trace(id, signal),
  });
  if (!request.data) return <ResourceState error={request.error} />;
  const trace = request.data;
  return (
    <>
      <div className="row toolbar">
        <button className="ghost" onClick={() => navigate({ view: "traces" })}>
          ← Trace explorer
        </button>
        <button
          className="secondary"
          onClick={() => navigate({ view: "graph", id })}
        >
          See evidence graph →
        </button>
      </div>
      <Card title={traceTitle(trace)}>
        <p className="mono">{id}</p>
        {typeof trace.data.repo === "string" && (
          <p>Repository: {trace.data.repo}</p>
        )}
        {[true, false, 0, 1].includes(
          trace.data.resolved as boolean | number,
        ) && (
          <p>
            Recorded outcome: {trace.data.resolved ? "Passed" : "Failed"} ·
            source field /resolved
          </p>
        )}
        {typeof trace.data.exit_status === "string" && (
          <p>Agent exit status: {trace.data.exit_status}</p>
        )}
        <p className="muted">
          Original imported evidence. Finding quotes resolve against this
          record.
        </p>
      </Card>
      <Conversation key={id} trace={trace} />
      <Card title="Complete original record">
        <Details title="All fields and metadata">
          <JsonView value={trace.data} />
        </Details>
      </Card>
    </>
  );
}
