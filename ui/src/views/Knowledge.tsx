import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Knowledge } from "../contracts";
import {
  ActionButton,
  Badge,
  Card,
  Field,
  JsonView,
  ResourceState,
} from "../components/shared";

function KnowledgeEntry({ entry }: { entry: Knowledge }) {
  const [note, setNote] = useState("");
  return (
    <div className="item">
      <div className="item-head">
        <h3>{entry.title}</h3>
        <Badge value={entry.status} />
      </div>
      <small>
        {entry.source} · revision {entry.revision}
      </small>
      <JsonView value={entry.content} />
      <Field
        label={`Review note for ${entry.title}`}
        value={note}
        onChange={setNote}
      />
      <div className="row controls">
        <ActionButton
          action={() => api.reviewKnowledge(entry.id, "accepted", note)}
        >
          Accept
        </ActionButton>
        <ActionButton
          className="danger"
          action={() => api.reviewKnowledge(entry.id, "rejected", note)}
        >
          Reject
        </ActionButton>
      </div>
    </div>
  );
}
export function KnowledgeView() {
  const request = useQuery({
    queryKey: ["artifacts", "knowledge"],
    queryFn: ({ signal }) => api.artifacts("knowledge", signal),
  });
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("");
  const [content, setContent] = useState("");
  return (
    <>
      {request.data ? (
        <Card title="Your reviewed context">
          <p className="muted">
            Accepted entries inform investigations. Changes make existing task
            context stale until reviewed again.
          </p>
          {request.data.map((entry) => (
            <KnowledgeEntry
              key={`${entry.id}-${entry.revision}`}
              entry={entry}
            />
          ))}
        </Card>
      ) : (
        <ResourceState error={request.error} />
      )}
      <Card title="Add project knowledge">
        <div className="stack">
          <Field label="Title" value={title} onChange={setTitle} />
          <Field
            label="Source / reference"
            value={source}
            onChange={setSource}
          />
          <Field
            label="Policy, context or success criteria"
            multiline
            value={content}
            onChange={setContent}
          />
          <ActionButton
            action={() => api.addKnowledge(title, source, content)}
            onSuccess={() => {
              setTitle("");
              setSource("");
              setContent("");
            }}
          >
            Save draft knowledge
          </ActionButton>
        </div>
      </Card>
    </>
  );
}
