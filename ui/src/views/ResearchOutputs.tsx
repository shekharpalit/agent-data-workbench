import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Investigation, ResearchArtifact } from "../contracts";
import {
  ActionButton,
  Badge,
  Bars,
  Card,
  Details,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";

async function download(id: string, artifact: ResearchArtifact) {
  const blob = await api.researchFile(id, artifact.id);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = artifact.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ResearchFiles({ item }: { item: Investigation }) {
  if (!item.attachments?.length) return null;
  return (
    <Card title="Research outputs">
      {item.attachments.map((artifact) => (
        <div className="item" key={artifact.id}>
          <div className="item-head">
            <h3>{artifact.title}</h3>
            <Badge value={artifact.kind} />
          </div>
          {artifact.chart && (
            <>
              <p>{artifact.chart.description}</p>
              <Bars
                values={artifact.chart.values.map((v) => ({
                  value: v.label,
                  count: v.value,
                }))}
                total={Math.max(
                  0,
                  ...artifact.chart.values.map((v) => v.value),
                )}
              />
            </>
          )}
          <p className="muted">
            {artifact.filename} · {artifact.bytes.toLocaleString()} bytes
          </p>
          <ActionButton
            className="ghost"
            action={() => download(item.id, artifact)}
          >
            Download {artifact.title}
          </ActionButton>
        </div>
      ))}
    </Card>
  );
}

export function ResearchProgress({ item }: { item: Investigation }) {
  const [after, setAfter] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const outcomes = useQuery({
    queryKey: ["research-outcomes", item.id, after],
    queryFn: ({ signal }) => api.researchOutcomes(item.id, after, signal),
    refetchInterval: item.active ? 2000 : false,
  });
  const journal = useQuery({
    queryKey: ["research-journal", item.id, offset],
    queryFn: ({ signal }) => api.researchJournal(item.id, offset, signal),
    refetchInterval: item.active ? 2000 : false,
  });
  return (
    <>
      <Card title="Record outcomes">
        <p className="muted">
          Each result records its analysis method. A completed record means an
          outcome was saved; its correctness still needs evaluation.
        </p>
        {outcomes.data ? (
          <>
            <Table
              headings={["Record", "Status", "Method", "Outcome"]}
              rows={outcomes.data.records.map((r) => ({
                key: r.trace_id,
                cells: [
                  r.trace_id,
                  <Badge value={r.status} />,
                  r.method ? (
                    <Details title="Review method">
                      <p>{r.method}</p>
                    </Details>
                  ) : (
                    "—"
                  ),
                  <Details title="Inspect">
                    <JsonView
                      value={r.error === null ? r.output : { error: r.error }}
                    />
                  </Details>,
                ],
              }))}
            />
            <div className="row">
              <button
                className="ghost"
                disabled={after === null}
                onClick={() => setAfter(null)}
              >
                First page
              </button>
              <button
                className="ghost"
                disabled={outcomes.data.next_cursor === null}
                onClick={() => setAfter(outcomes.data!.next_cursor)}
              >
                Next records →
              </button>
            </div>
          </>
        ) : (
          <ResourceState error={outcomes.error} />
        )}
      </Card>
      <Card title="Investigation journal">
        {journal.data ? (
          <>
            <p className="muted">{journal.data.total} saved events</p>
            {journal.data.items.map((e) => (
              <Details key={e.id} title={`${e.kind} — ${e.note}`}>
                <p className="muted">{e.at}</p>
                <JsonView value={e.details} />
              </Details>
            ))}
            <div className="row">
              <button
                className="ghost"
                disabled={offset === 0}
                onClick={() => setOffset(0)}
              >
                First page
              </button>
              <button
                className="ghost"
                disabled={journal.data.next_offset === null}
                onClick={() => setOffset(journal.data!.next_offset!)}
              >
                Next events →
              </button>
            </div>
          </>
        ) : (
          <ResourceState error={journal.error} />
        )}
      </Card>
    </>
  );
}
