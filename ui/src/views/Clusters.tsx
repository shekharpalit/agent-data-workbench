import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { ClusterRequest, SearchQuery } from "../contracts";
import {
  Card,
  Field,
  ResourceState,
  Details,
  JsonView,
  submit,
} from "../components/shared";

export function ClustersView({
  query,
  onMembers,
}: {
  query: SearchQuery;
  onMembers: (ids: string[]) => void;
}) {
  const [pointer, setPointer] = useState("/input");
  const [threshold, setThreshold] = useState("0.55");
  const [limit, setLimit] = useState("100");
  const [active, setActive] = useState<ClusterRequest | null>(null);
  const request = useQuery({
    queryKey: ["clusters", active],
    queryFn: ({ signal }) => api.clusters(active!, signal),
    enabled: active !== null,
  });
  return (
    <>
      <Card title="Find recurring patterns">
        <p>
          Group matching traces by shared language, then inspect the evidence
          within each group.
        </p>
        <form
          onSubmit={submit(() =>
            setActive({
              query,
              pointer,
              threshold: Number(threshold),
              limit: Number(limit),
            }),
          )}
        >
          <div className="row">
            <Field
              label="Text field (JSON pointer; empty uses the record)"
              value={pointer}
              onChange={setPointer}
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
              label="Maximum traces (2–200)"
              type="number"
              min={2}
              max={200}
              value={limit}
              onChange={setLimit}
            />
            <button disabled={request.isFetching}>Group traces</button>
          </div>
        </form>
        <p className="muted">
          Uses the current search filters. Higher thresholds create tighter
          groups. Computed locally without a model call.
        </p>
        <Details title="Current search filters">
          <JsonView value={query} />
        </Details>
      </Card>
      {active &&
        (request.data ? (
          <>
            <Card
              title={`${request.data.clusters.length} groups from ${request.data.clustered} traces`}
            >
              <p>
                {request.data.sampled} inspected / {request.data.eligible}{" "}
                matched · {request.data.omitted_ids.length} without usable text
              </p>
              <p className="scope-note">{request.data.scope}</p>
              <p className="muted">
                Text is capped at{" "}
                {request.data.text_limit_chars.toLocaleString()} characters per
                trace · {request.data.text_truncated_ids.length} traces clipped.
              </p>
              {request.data.text_truncated_ids.length > 0 && (
                <Details title="Traces with clipped text">
                  <JsonView value={request.data.text_truncated_ids} />
                </Details>
              )}
              {request.data.truncated && (
                <p className="scope-note">
                  This is a bounded selection, not a census of all matching
                  data.
                </p>
              )}
            </Card>
            <div className="cluster-grid">
              {request.data.clusters.map((group, i) => (
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
                  <p className="muted mono">
                    {group.trace_ids.slice(0, 3).join(", ")}
                    {group.count > 3 ? "…" : ""}
                  </p>
                  <button
                    className="secondary"
                    onClick={() => onMembers(group.trace_ids)}
                  >
                    Inspect members →
                  </button>
                </Card>
              ))}
            </div>
            {request.data.clusters.length === 0 && (
              <Card title="No usable text">
                <p>
                  Choose a field containing text or clear the pointer to inspect
                  the full records.
                </p>
              </Card>
            )}
          </>
        ) : (
          <ResourceState error={request.error} />
        ))}
    </>
  );
}
