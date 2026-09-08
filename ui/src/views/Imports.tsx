import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Route } from "../contracts";
import type { DatasetImport, DatasetSource } from "../data-contracts";
import {
  ActionButton,
  Badge,
  Card,
  Details,
  Field,
  JsonView,
  ResourceState,
} from "../components/shared";

const empty: DatasetImport = {
  dataset: "",
  configuration: null,
  split: "train",
  revision: "main",
  id_pointer: "",
  group_pointer: "/thread_id",
  stratum_pointer: "/agent_type",
  limit: null,
};
export function ImportsView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const [config, setConfig] = useState<DatasetImport>(empty);
  const [maximum, setMaximum] = useState("");
  const [preview, setPreview] = useState<DatasetSource | null>(null);
  const [started, setStarted] = useState(false);
  const receipts = useQuery({
    queryKey: ["imports"],
    queryFn: ({ signal }) => api.imports(signal),
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: ({ signal }) => api.jobs(signal),
  });
  const busy = jobs.data?.some((job) => job.status === "running");
  function update(patch: Partial<DatasetImport>) {
    setConfig({ ...config, ...patch });
    setPreview(null);
    setStarted(false);
  }
  function selection(): DatasetImport {
    const limit = maximum.trim() ? Number(maximum) : null;
    if (!config.dataset.trim())
      throw new Error("Enter a Hugging Face dataset ID.");
    if (limit !== null && (!Number.isInteger(limit) || limit < 1))
      throw new Error(
        "Maximum rows must be a positive integer or empty for all rows.",
      );
    return { ...config, limit };
  }
  return (
    <>
      <Card title="Bring your traces into one workspace">
        <p>
          Import a Hugging Face dataset directly. Each row becomes one trace,
          with all fields and messages preserved. Data and import receipts stay
          in your local project.
        </p>
        <button
          className="secondary"
          onClick={() => {
            setConfig({
              ...empty,
              dataset: "nebius/SWE-rebench-openhands-trajectories",
              id_pointer: "/trajectory_id",
              group_pointer: "/instance_id",
              stratum_pointer: "/repo",
            });
            setPreview(null);
          }}
        >
          Use SWE-rebench / OpenHands preset
        </button>
        <p className="muted">
          The preset maps attempts to their issue and repository. It does not
          start a download.
        </p>
        <Field
          label="Hugging Face dataset ID"
          value={config.dataset}
          onChange={(dataset) => update({ dataset })}
          placeholder="organization/dataset"
        />
        <div className="row">
          <Field
            label="Configuration (optional)"
            value={config.configuration || ""}
            onChange={(configuration) =>
              update({ configuration: configuration || null })
            }
          />
          <Field
            label="Split"
            value={config.split}
            onChange={(split) => update({ split })}
          />
          <Field
            label="Revision"
            value={config.revision}
            onChange={(revision) => update({ revision })}
          />
        </div>
        <div className="row">
          <Field
            label="Trace ID field (optional)"
            value={config.id_pointer}
            onChange={(id_pointer) => update({ id_pointer })}
            placeholder="Empty generates stable UUIDs"
          />
          <Field
            label="Same-task group field"
            value={config.group_pointer}
            onChange={(group_pointer) => update({ group_pointer })}
            placeholder="/instance_id"
          />
          <Field
            label="Category field"
            value={config.stratum_pointer}
            onChange={(stratum_pointer) => update({ stratum_pointer })}
            placeholder="/repo"
          />
        </div>
        <Field
          label="Maximum rows (optional)"
          type="number"
          min={1}
          value={maximum}
          onChange={(value) => {
            setMaximum(value);
            setPreview(null);
          }}
          placeholder="All rows in this split"
        />
        <p className="scope-note">
          {maximum.trim()
            ? `Explicit selection: first ${maximum} rows in dataset order. Every selected row is imported in full.`
            : "Selection: the entire split. No default row or text limit."}
        </p>
        <div className="row">
          <ActionButton
            className="secondary"
            action={async () => {
              const result = await api.inspectDataset(selection());
              setPreview(result.source);
              setConfig(result.config);
            }}
          >
            Inspect source & schema
          </ActionButton>
          {!busy && (
            <ActionButton
              action={async () => {
                await api.importDataset(selection());
                setStarted(true);
              }}
            >
              Import dataset
            </ActionButton>
          )}
          {busy && (
            <p role="status">
              An operation is running. Import will be available when it
              finishes.
            </p>
          )}
        </div>
        {started && (
          <p role="status">
            Import submitted. Progress and any errors appear above. Results
            refresh automatically.
          </p>
        )}
        {preview && (
          <div className="item">
            <h3>Resolved source</h3>
            <p>
              {preview.dataset} · {preview.split} ·{" "}
              {Object.keys(preview.features).length} fields
            </p>
            <p className="mono">Revision {preview.revision}</p>
            <p>License: {String(preview.license || "See dataset card")}</p>
            <Details title="Complete dataset schema">
              <JsonView value={preview.features} />
            </Details>
          </div>
        )}
      </Card>
      <Card title="Import history">
        {receipts.data ? (
          <>
            {[...receipts.data]
              .sort((a, b) => b.created_at.localeCompare(a.created_at))
              .map((receipt) => (
                <div className="item" key={receipt.id}>
                  <div className="item-head">
                    <h3>{receipt.source.dataset}</h3>
                    <Badge value={receipt.status} />
                  </div>
                  <p>
                    {receipt.source.split} ·{" "}
                    {receipt.config.limit === null
                      ? "Entire split"
                      : `First ${receipt.config.limit} rows selected`}
                  </p>
                  {receipt.result && (
                    <p>
                      {receipt.result.added} added · {receipt.result.unchanged}{" "}
                      already present · {receipt.result.total} total traces
                    </p>
                  )}
                  {receipt.error && (
                    <p className="error-text" role="alert">
                      {receipt.error}
                    </p>
                  )}
                  <Details title="Source revision and exact import receipt">
                    <JsonView value={receipt} />
                  </Details>
                </div>
              ))}
            {!receipts.data.length && (
              <p className="muted">
                No Hugging Face imports yet. Existing file imports remain
                available in Trace explorer.
              </p>
            )}
          </>
        ) : (
          <ResourceState error={receipts.error} />
        )}
        <div className="row">
          <button onClick={() => navigate({ view: "graph" })}>
            Understand this dataset →
          </button>
          <button
            className="secondary"
            onClick={() => navigate({ view: "traces" })}
          >
            Inspect traces →
          </button>
        </div>
      </Card>
      <Details title="Import local JSON and JSONL files">
        <p>
          From your terminal, pass one or more files or directories. The default
          treats each JSONL file as one ordered agent run.
        </p>
        <pre>agent-data-workbench ingest /path/to/project /path/to/traces</pre>
        <p>
          For exports containing one complete trace per row, add{" "}
          <code>--layout records</code>. The entire batch rolls back on invalid
          or conflicting data.
        </p>
      </Details>
    </>
  );
}
