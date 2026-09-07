import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Json, ReviewStatus } from "../contracts";
import { ActionButton, Choice, Field } from "../components/shared";
export const lines = (value: string) =>
  value
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
export function jsonObject(value: string, label: string): Record<string, Json> {
  const parsed: unknown = JSON.parse(value);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))
    throw new Error(`${label} must be a JSON object.`);
  return parsed as Record<string, Json>;
}
export function useWorkflow() {
  return useQuery({
    queryKey: ["workflow"],
    queryFn: ({ signal }) => api.workflow(signal),
  });
}
export function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder = "Choose…",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { id: string; label: string }[];
  placeholder?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option value={o.id} key={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
export function VersionReview({
  review,
}: {
  review: (
    status: ReviewStatus,
    note: string,
    reviewer: string,
  ) => Promise<unknown>;
}) {
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<ReviewStatus>("accepted");
  return (
    <div className="stack">
      <div className="row">
        <Field label="Reviewer" value={reviewer} onChange={setReviewer} />
        <Choice
          label="Decision"
          value={status}
          options={["accepted", "rejected", "draft"]}
          onChange={setStatus}
        />
      </div>
      <Field label="Review note" value={note} onChange={setNote} multiline />
      <ActionButton
        action={() => {
          if (!reviewer.trim() || !note.trim())
            throw new Error("Enter a reviewer and review note.");
          return review(status, note, reviewer);
        }}
      >
        Save review
      </ActionButton>
    </div>
  );
}
