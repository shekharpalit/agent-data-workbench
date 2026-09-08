import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { ClusterRequest, Route, SearchQuery } from "../contracts";
import {
  Card,
  Field,
  ResourceState,
  Details,
  JsonView,
  submit,
} from "../components/shared";

const ClusterGraph = lazy(() => import("../components/graphs/ClusterGraph"));

export function ClustersView({
  query,
  onMembers,
  navigate,
}: {
  query: SearchQuery;
  onMembers: (ids: string[]) => void;
  navigate: (route: Route) => void;
}) {
  const [pointer, setPointer] = useState("");
  const [threshold, setThreshold] = useState("0.55");
  const [limit, setLimit] = useState("");
  const [active, setActive] = useState<ClusterRequest>({
    query,
    pointer: "",
    threshold: 0.55,
    limit: null,
  });
  const request = useQuery({
    queryKey: ["clusters", active],
    queryFn: ({ signal }) => api.clusters(active, signal),
  });
  const data = request.data;
  return (
    <>
      <Card title="Find recurring patterns">
        <p>
          Group traces by shared language and inspect the events behind each
          group.
        </p>
        <form
          onSubmit={submit(() =>
            setActive({
              query,
              pointer,
              threshold: Number(threshold),
              limit: limit.trim() ? Number(limit) : null,
            }),
          )}
        >
          <div className="row">
            <Field
              label="Text field (JSON pointer; empty uses the record)"
              value={pointer}
              onChange={setPointer}
              placeholder="All trace content"
            />
            <Field
              label="Similarity threshold (0.1–1)"
              type="number"
              min={0.1}
              max={1}
              value={threshold}
              onChange={setThreshold}
            />
            <Field
              label="Maximum traces (optional)"
              type="number"
              min={2}
              value={limit}
              onChange={setLimit}
              placeholder="All matching traces"
            />
            <button disabled={request.isFetching}>Group traces</button>
          </div>
        </form>
        <p className="muted">
          Uses current search filters and complete selected text. Higher
          thresholds create tighter groups. Computed locally without a model
          call.
        </p>
        <Details title="Current search filters">
          <JsonView value={query} />
        </Details>
      </Card>
      {data ? (
        <>
          <Card
            title={`${data.clusters.length} groups from ${data.clustered} traces`}
          >
            <p>
              {data.sampled} inspected / {data.eligible} matched ·{" "}
              {data.omitted_ids.length} without usable text
            </p>
            <p className="scope-note">{data.scope}</p>
            {data.truncated && (
              <p className="scope-note">
                Your maximum selected {data.sampled} of {data.eligible} matching
                traces. Clear the maximum to include all matches.
              </p>
            )}
            {data.omitted_ids.length > 0 && (
              <Details title="Traces without the selected field or usable text">
                <JsonView value={data.omitted_ids} />
              </Details>
            )}
          </Card>
          {data.clusters.length > 0 && (
            <Suspense fallback={<ResourceState />}>
              <ClusterGraph
                key={`${JSON.stringify(active)}:${data.source_sha256}`}
                clusters={data.clusters}
                onMembers={onMembers}
                navigate={navigate}
              />
            </Suspense>
          )}
          <div className="cluster-grid">
            {data.clusters.map((group, i) => (
              <Card key={group.id} title={group.label || `Group ${i + 1}`}>
                <div className="cluster-number">
                  {String(i + 1).padStart(2, "0")}
                  <span>{group.count} traces</span>
                </div>
                <div className="pill-group">
                  {group.terms.map((term) => (
                    <span className="term" key={term}>
                      {term}
                    </span>
                  ))}
                </div>
                <Details title={`All ${group.count} trace IDs`}>
                  <JsonView value={group.trace_ids} />
                </Details>
                <button
                  className="secondary"
                  onClick={() => onMembers(group.trace_ids)}
                >
                  Inspect members →
                </button>
              </Card>
            ))}
          </div>
          {data.clusters.length === 0 && (
            <Card
              title={
                data.eligible
                  ? "No usable text in the selected field"
                  : "No matching traces"
              }
            >
              <p>
                {data.eligible
                  ? "Clear the text field to use complete records, or choose a JSON pointer present in these traces."
                  : "Reset the search filters or import traces to start clustering."}
              </p>
            </Card>
          )}
        </>
      ) : (
        <ResourceState error={request.error} />
      )}
    </>
  );
}
