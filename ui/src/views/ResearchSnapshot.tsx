import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type {
  Evidence,
  Investigation,
  Json,
  ResearchSearch,
} from "../contracts";
import {
  ActionButton,
  Badge,
  Card,
  Choice,
  Field,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";

function RecordReview({
  item,
  traceId,
  initialPointer = "",
  review = true,
}: {
  item: Investigation;
  traceId: string;
  initialPointer?: string;
  review?: boolean;
}) {
  const [pointer, setPointer] = useState(initialPointer);
  const [query, setQuery] = useState({ pointer: initialPointer, offset: 0 });
  const [kind, setKind] = useState<"completed" | "failed">("completed");
  const [note, setNote] = useState("");
  const [method, setMethod] = useState("Human review");
  const [structured, setStructured] = useState(false);
  const [output, setOutput] = useState("{}");
  const [saved, setSaved] = useState(false);
  const request = useQuery({
    queryKey: ["research-trace", item.id, traceId, query],
    queryFn: ({ signal }) =>
      api.researchTrace(item.id, traceId, query.pointer, query.offset, signal),
  });
  const editable = review && !item.active && item.status !== "complete";
  return (
    <div className="stack">
      <h3>{traceId}</h3>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setQuery({ pointer, offset: 0 });
        }}
      >
        <Field
          label="JSON pointer (blank for whole record)"
          value={pointer}
          onChange={setPointer}
          placeholder="/messages/0/content"
        />
        <button type="submit" className="secondary">
          Read field
        </button>
      </form>
      {request.data ? (
        <>
          <JsonView value={request.data.content} />
          <p className="muted">
            Characters {request.data.offset.toLocaleString()}–
            {(
              request.data.offset + request.data.content.length
            ).toLocaleString()}{" "}
            of {request.data.total_chars.toLocaleString()}. Evidence quotes must
            match the selected field exactly.
          </p>
          <div className="row">
            <button
              className="ghost"
              disabled={query.offset === 0}
              onClick={() => setQuery({ ...query, offset: 0 })}
            >
              Start of field
            </button>
            <button
              className="ghost"
              disabled={request.data.next_offset === null}
              onClick={() =>
                setQuery({ ...query, offset: request.data!.next_offset! })
              }
            >
              Read next part →
            </button>
          </div>
        </>
      ) : (
        <ResourceState error={request.error} />
      )}
      {editable && (
        <>
          <h3>Save a record outcome</h3>
          <Choice
            label="Review outcome"
            value={kind}
            options={["completed", "failed"]}
            onChange={(value) => {
              setKind(value);
              setSaved(false);
            }}
          />
          <Field
            label="Review method"
            value={method}
            onChange={(value) => {
              setMethod(value);
              setSaved(false);
            }}
          />
          {kind === "completed" && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={structured}
                onChange={(event) => {
                  setStructured(event.target.checked);
                  setSaved(false);
                }}
              />
              Use a structured JSON outcome
            </label>
          )}
          {kind === "completed" && structured ? (
            <Field
              label="Outcome JSON object"
              multiline
              value={output}
              onChange={(value) => {
                setOutput(value);
                setSaved(false);
              }}
            />
          ) : (
            <Field
              label={
                kind === "failed"
                  ? "What prevented review?"
                  : "Your observation"
              }
              multiline
              value={note}
              onChange={(value) => {
                setNote(value);
                setSaved(false);
              }}
            />
          )}
          <ActionButton
            action={async () => {
              let result: Record<string, Json> | null = null;
              if (kind === "completed") {
                if (structured) {
                  const value: unknown = JSON.parse(output);
                  if (
                    !value ||
                    typeof value !== "object" ||
                    Array.isArray(value)
                  )
                    throw new Error("Outcome must be a JSON object.");
                  result = value as Record<string, Json>;
                } else {
                  if (!note.trim())
                    throw new Error("Add your observation before saving.");
                  result = { note };
                }
              } else if (!note.trim())
                throw new Error("Describe what prevented review.");
              await api.recordResearch(item.id, [
                {
                  trace_id: traceId,
                  output: result,
                  error: kind === "failed" ? note : null,
                  method,
                },
              ]);
            }}
            onSuccess={() => setSaved(true)}
          >
            Save record outcome
          </ActionButton>
          {saved && (
            <p role="status">
              Outcome saved. You can revisit and update it before publishing.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export function ResearchSnapshot({ item }: { item: Investigation }) {
  const [text, setText] = useState("");
  const [stratum, setStratum] = useState("");
  const [pending, setPending] = useState(false);
  const [query, setQuery] = useState<ResearchSearch>({
    text: "",
    stratum: "",
    after: null,
    pending_only: false,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const request = useQuery({
    queryKey: [
      "research-search",
      item.id,
      query,
      item.coverage.completed,
      item.coverage.failed,
      item.coverage.pending,
    ],
    queryFn: ({ signal }) => api.searchResearch(item.id, query, signal),
  });
  return (
    <Card title="Research dataset">
      <p className="muted">
        Search the snapshot captured for this investigation. New imports do not
        change these records.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setQuery({ text, stratum, after: null, pending_only: pending });
        }}
      >
        <div className="row">
          <Field label="Search this snapshot" value={text} onChange={setText} />
          <Field label="Stratum" value={stratum} onChange={setStratum} />
        </div>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={pending}
            onChange={(event) => setPending(event.target.checked)}
          />
          Only pending or failed records
        </label>
        <button type="submit">Search records</button>
      </form>
      {request.data ? (
        <>
          <Table
            headings={["Record", "Stratum", "Status"]}
            rows={request.data.records.map((row) => ({
              key: row.trace_id,
              cells: [
                <button
                  className="ghost"
                  aria-pressed={selected === row.trace_id}
                  onClick={() => setSelected(row.trace_id)}
                >
                  {row.trace_id}
                </button>,
                row.stratum || "—",
                <Badge value={row.status} />,
              ],
            }))}
          />
          {!request.data.records.length && (
            <p className="muted">No records match these filters.</p>
          )}
          <div className="row controls">
            <button
              className="ghost"
              disabled={query.after === null}
              onClick={() => setQuery({ ...query, after: null })}
            >
              First records
            </button>
            <button
              className="ghost"
              disabled={request.data.next_cursor === null}
              onClick={() =>
                setQuery({ ...query, after: request.data!.next_cursor })
              }
            >
              Next matching records →
            </button>
          </div>
        </>
      ) : (
        <ResourceState error={request.error} />
      )}
      {selected && (
        <div className="item">
          <RecordReview key={selected} item={item} traceId={selected} />
        </div>
      )}
    </Card>
  );
}

export function SnapshotCitation({
  item,
  evidence,
}: {
  item: Investigation;
  evidence: Evidence;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        className="ghost"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {evidence.trace_id} · {evidence.pointer || "Whole record"}
      </button>
      {open && (
        <RecordReview
          key={`${evidence.trace_id}:${evidence.pointer}`}
          item={item}
          traceId={evidence.trace_id}
          initialPointer={evidence.pointer}
          review={false}
        />
      )}
    </>
  );
}
