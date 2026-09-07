import { useState } from "react";
import { api } from "../api";
import type {
  Evidence,
  Finding,
  Investigation,
  ResearchChart,
  ResearchResult,
} from "../contracts";
import {
  ActionButton,
  Card,
  Choice,
  Details,
  Field,
} from "../components/shared";

function emptyResult(): ResearchResult {
  return {
    analysis: { summary: "", findings: [], cases: [], limitations: [] },
    signals: [],
    proposals: [],
    open_questions: [],
  };
}

function CitationEditor({
  citation,
  onChange,
  onRemove,
  number,
}: {
  citation: Evidence;
  onChange: (value: Evidence) => void;
  onRemove: () => void;
  number: number;
}) {
  return (
    <fieldset className="stack">
      <legend>Citation {number}</legend>
      <div className="row">
        <Field
          label="Trace ID"
          value={citation.trace_id}
          onChange={(trace_id) => onChange({ ...citation, trace_id })}
        />
        <Field
          label="JSON pointer"
          value={citation.pointer}
          onChange={(pointer) => onChange({ ...citation, pointer })}
          placeholder="/messages/0/content"
        />
      </div>
      <Field
        label="Exact quote"
        multiline
        value={citation.quote}
        onChange={(quote) => onChange({ ...citation, quote })}
      />
      <button type="button" className="ghost" onClick={onRemove}>
        Remove citation
      </button>
    </fieldset>
  );
}

function FindingEditor({
  finding,
  onChange,
  onRemove,
  linked,
  number,
}: {
  finding: Finding;
  onChange: (value: Finding) => void;
  onRemove: () => void;
  linked: boolean;
  number: number;
}) {
  return (
    <fieldset className="stack">
      <legend>Finding {number}</legend>
      <Field
        label="Finding title"
        value={finding.title}
        onChange={(title) => onChange({ ...finding, title })}
      />
      <div className="row">
        <Choice
          label="Category"
          value={finding.category}
          options={["failure", "opportunity"]}
          onChange={(category) => onChange({ ...finding, category })}
        />
        <Choice
          label="Confidence"
          value={finding.confidence}
          options={["observation", "hypothesis"]}
          onChange={(confidence) => onChange({ ...finding, confidence })}
        />
      </div>
      <Field
        label="Explanation"
        multiline
        value={finding.explanation}
        onChange={(explanation) => onChange({ ...finding, explanation })}
      />
      <Field
        label="Recommendation"
        multiline
        value={finding.recommendation}
        onChange={(recommendation) => onChange({ ...finding, recommendation })}
      />
      {finding.evidence.map((citation, index) => (
        <CitationEditor
          key={index}
          number={index + 1}
          citation={citation}
          onChange={(value) =>
            onChange({
              ...finding,
              evidence: finding.evidence.map((old, i) =>
                i === index ? value : old,
              ),
            })
          }
          onRemove={() =>
            onChange({
              ...finding,
              evidence: finding.evidence.filter((_, i) => i !== index),
            })
          }
        />
      ))}
      <div className="row">
        <button
          type="button"
          className="secondary"
          onClick={() =>
            onChange({
              ...finding,
              evidence: [
                ...finding.evidence,
                { trace_id: "", pointer: "", quote: "" },
              ],
            })
          }
        >
          Add citation
        </button>
        <button
          type="button"
          className="ghost"
          disabled={linked}
          onClick={onRemove}
        >
          Remove finding
        </button>
      </div>
      {linked && (
        <p className="muted">
          This finding is referenced by a saved case, signal or proposal. Its ID
          and references are retained when you edit it.
        </p>
      )}
    </fieldset>
  );
}

function FindingsEditor({
  item,
  onComplete,
}: {
  item: Investigation;
  onComplete: () => void;
}) {
  const [draft, setDraft] = useState<ResearchResult["analysis"] | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  function start() {
    setDraft(structuredClone((item.result || emptyResult()).analysis));
    setMessage("");
  }
  async function publish(complete: boolean) {
    if (!draft) return;
    setSaving(true);
    setMessage("");
    // Only the fields this form owns are replaced. Polling can refresh the other
    // outputs while local edits remain intact.
    const current = item.result || emptyResult();
    const result: ResearchResult = {
      ...current,
      analysis: {
        ...current.analysis,
        summary: draft.summary,
        findings: draft.findings,
      },
    };
    try {
      await api.publishResearch(item.id, result, complete);
      if (complete) onComplete();
      else
        setMessage(
          "Draft saved. You can continue researching before publishing.",
        );
    } finally {
      setSaving(false);
    }
  }
  return (
    <Card title="Write research findings">
      <p className="muted">
        Connect each finding to exact quotes from this investigation’s snapshot.
        Saving retains existing cases, signals, proposals, limitations and open
        questions.
      </p>
      {draft ? (
        <fieldset className="stack" disabled={saving}>
          <legend>Findings draft</legend>
          <Field
            label="Research summary"
            multiline
            value={draft.summary}
            onChange={(summary) => setDraft({ ...draft, summary })}
          />
          {draft.findings.map((finding, index) => (
            <FindingEditor
              key={finding.id}
              finding={finding}
              number={index + 1}
              linked={Boolean(
                item.result?.analysis.cases.some((c) =>
                  c.finding_ids.includes(finding.id),
                ) ||
                item.result?.signals.some((s) => s.finding_id === finding.id) ||
                item.result?.proposals.some((p) =>
                  p.finding_ids.includes(finding.id),
                ),
              )}
              onChange={(value) =>
                setDraft({
                  ...draft,
                  findings: draft.findings.map((old) =>
                    old.id === finding.id ? value : old,
                  ),
                })
              }
              onRemove={() =>
                setDraft({
                  ...draft,
                  findings: draft.findings.filter(
                    (old) => old.id !== finding.id,
                  ),
                })
              }
            />
          ))}
          <button
            type="button"
            className="secondary"
            onClick={() =>
              setDraft({
                ...draft,
                findings: [
                  ...draft.findings,
                  {
                    id: crypto.randomUUID(),
                    title: "",
                    category: "failure",
                    confidence: "observation",
                    explanation: "",
                    recommendation: "",
                    evidence: [{ trace_id: "", pointer: "", quote: "" }],
                  },
                ],
              })
            }
          >
            Add finding
          </button>
          {item.mode === "complete" && (
            <p className="muted">
              Final publication requires a saved outcome for every record and no
              pending or failed records. Drafts can be saved at any time.
            </p>
          )}
          <p className="muted">
            Publishing final findings completes this investigation. Continue
            editing with Save draft until your research is ready.
          </p>
          <div className="row controls">
            <ActionButton action={() => publish(false)} className="secondary">
              Save findings draft
            </ActionButton>
            <ActionButton action={() => publish(true)}>
              Publish final findings
            </ActionButton>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setDraft(null);
                setMessage("");
              }}
            >
              Cancel editing
            </button>
          </div>
          {message && <p role="status">{message}</p>}
        </fieldset>
      ) : (
        <button type="button" onClick={start}>
          {item.result ? "Edit findings" : "Write findings"}
        </button>
      )}
    </Card>
  );
}

function ResearchNote({ id }: { id: string }) {
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  return (
    <Card title="Research notes">
      <Field
        label="Journal note"
        multiline
        value={note}
        onChange={(value) => {
          setNote(value);
          setMessage("");
        }}
        placeholder="What did you inspect, learn or decide to investigate next?"
      />
      <ActionButton
        action={async () => {
          await api.researchCheckpoint(id, note);
          setNote((current) => (current === note ? "" : current));
          setMessage("Note saved to the investigation journal.");
        }}
      >
        Save journal note
      </ActionButton>
      {message && <p role="status">{message}</p>}
    </Card>
  );
}

function ChartEditor({ id }: { id: string }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [rows, setRows] = useState([{ label: "", value: "" }]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  async function save() {
    if (!title.trim()) throw new Error("Enter a chart title.");
    if (
      !rows.length ||
      rows.some(
        (row) =>
          !row.label.trim() ||
          !row.value.trim() ||
          !Number.isFinite(Number(row.value)) ||
          Number(row.value) < 0,
      )
    ) {
      throw new Error(
        "Each chart row needs a label and a finite value of zero or more.",
      );
    }
    const chart: ResearchChart = {
      title,
      description,
      values: rows.map((row) => ({
        label: row.label,
        value: Number(row.value),
      })),
    };
    setSaving(true);
    setMessage("");
    try {
      await api.createResearchChart(id, chart);
      setTitle("");
      setDescription("");
      setRows([{ label: "", value: "" }]);
      setMessage("Chart saved to research outputs.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <Details title="Create a chart">
      <Card title="Bar chart">
        <fieldset className="stack" disabled={saving}>
          <legend>Chart data</legend>
          <Field label="Chart title" value={title} onChange={setTitle} />
          <Field
            label="Chart description"
            multiline
            value={description}
            onChange={setDescription}
          />
          {rows.map((row, index) => (
            <div className="row" key={index}>
              <Field
                label={`Label ${index + 1}`}
                value={row.label}
                onChange={(label) =>
                  setRows(
                    rows.map((old, i) =>
                      i === index ? { ...old, label } : old,
                    ),
                  )
                }
              />
              <Field
                label={`Value ${index + 1}`}
                type="number"
                min={0}
                value={row.value}
                onChange={(value) =>
                  setRows(
                    rows.map((old, i) =>
                      i === index ? { ...old, value } : old,
                    ),
                  )
                }
              />
              <button
                type="button"
                className="ghost"
                aria-label={`Remove chart row ${index + 1}`}
                onClick={() => setRows(rows.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </div>
          ))}
          <div className="row controls">
            <button
              type="button"
              className="secondary"
              onClick={() => setRows([...rows, { label: "", value: "" }])}
            >
              Add chart row
            </button>
            <ActionButton action={save}>Save chart</ActionButton>
          </div>
          {message && <p role="status">{message}</p>}
        </fieldset>
      </Card>
    </Details>
  );
}

export function ManualResearchEditor({ item }: { item: Investigation }) {
  const [complete, setComplete] = useState(false);
  if (item.status === "complete" || complete) return null;
  return (
    <div hidden={item.active}>
      <fieldset className="manual-research-editor" disabled={item.active}>
        <ResearchNote id={item.id} />
        <FindingsEditor item={item} onComplete={() => setComplete(true)} />
        <ChartEditor id={item.id} />
      </fieldset>
    </div>
  );
}
