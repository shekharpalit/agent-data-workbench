import { useState } from "react";
import type { Trace } from "../../contracts";
import { Card, Details, Field, JsonView } from "../shared";
import { traceMessages, object } from "./presentation";

export function Conversation({ trace }: { trace: Trace }) {
  const [search, setSearch] = useState("");
  const messages = traceMessages(trace);
  if (!messages.length) return null;
  const matching = messages
    .map((message, index) => ({ ...message, index }))
    .filter((message) =>
      JSON.stringify(message.record)
        .toLowerCase()
        .includes(search.toLowerCase()),
    );
  return (
    <Card title={`Conversation · ${messages.length} events`}>
      <p>
        Read messages and tool calls in source order. Open an event for its
        complete content and original JSON pointer.
      </p>
      <Field
        label="Search within this complete trace"
        value={search}
        onChange={setSearch}
        placeholder="Message text, a tool name, an error…"
      />
      <p className="muted">
        {matching.length} of {messages.length} events match. Expanding an event
        shows all its content.
      </p>
      <div className="trace-timeline">
        {matching.map((message) => (
          <details className="trace-event" key={message.pointer}>
            <summary>
              <span className="event-number">{message.index + 1}</span>
              <strong>{message.role.replaceAll("_", " ")}</strong>
              <code>{message.pointer}</code>
            </summary>
            <div className="event-body">
              <JsonView value={message.content} />
              {object(message.record)?.tool_calls && (
                <Details title="Tool calls and complete arguments">
                  <JsonView value={object(message.record)?.tool_calls} />
                </Details>
              )}
              <Details title="Original event and all metadata">
                <JsonView value={message.record} />
              </Details>
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}
