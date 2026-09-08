import type { Json, Trace } from "../../contracts";

export function object(value: Json | undefined): Record<string, Json> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null;
}
export function traceTitle(trace: Trace): string {
  const data = trace.data;
  for (const value of [
    data.instance_id,
    data.title,
    object(data.task)?.title,
    object(data.source)?.path,
    data.task_id,
  ]) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return trace.trace_id;
}
export interface TraceMessage {
  pointer: string;
  role: string;
  content: Json;
  record: Json;
}
export function traceMessages(trace: Trace): TraceMessage[] {
  for (const field of ["trajectory", "messages", "events", "steps"]) {
    const entries = trace.data[field];
    if (!Array.isArray(entries)) continue;
    return entries.map((entry, index) => {
      const original = object(entry);
      const record =
        object(original?.payload) || object(original?.message) || original;
      const role =
        record?.role ?? record?.source ?? record?.type ?? original?.type;
      return {
        pointer: `/${field}/${index}`,
        role: typeof role === "string" ? role : "Event",
        content: record?.content ?? record?.message ?? entry,
        record: entry,
      };
    });
  }
  if (Array.isArray(trace.data.trajectories)) {
    return trace.data.trajectories.flatMap((item, index) => {
      const data = object(object(item)?.data);
      if (!data) return [];
      return traceMessages({ trace_id: trace.trace_id, data }).map(
        (message) => ({
          ...message,
          pointer: `/trajectories/${index}/data${message.pointer}`,
        }),
      );
    });
  }
  return [];
}
