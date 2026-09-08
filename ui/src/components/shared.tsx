import {
  useId,
  useState,
  type FormEvent,
  type ReactNode,
  type CSSProperties,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Backend, Json } from "../contracts";

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value.replace(/[^a-z_-]/g, "")}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
export function JsonView({ value }: { value: unknown }) {
  return (
    <pre>
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
export function Details({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <details>
      <summary>{title}</summary>
      {children}
    </details>
  );
}
export function Field({
  label,
  value,
  onChange,
  multiline = false,
  type = "text",
  placeholder = "",
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  type?: string;
  placeholder?: string;
  min?: number;
  max?: number;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
      ) : (
        <input
          id={id}
          type={type}
          step={type === "number" ? "any" : undefined}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          min={min}
          max={max}
        />
      )}
    </div>
  );
}
export function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </div>
  );
}
export function Table({
  headings,
  rows,
}: {
  headings: string[];
  rows: { key: string; cells: ReactNode[] }[];
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {headings.map((title, i) => (
              <th key={`${title}-${i}`}>{title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              {row.cells.map((cell, i) => (
                <td key={i}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Bars({
  values,
  total,
  onSelect,
  colors,
}: {
  values: { value: Json; count: number }[];
  total: number;
  onSelect?: (value: Json) => void;
  colors?: Record<string, string>;
}) {
  return (
    <div>
      {values.map((item, index) => (
        <div className="bar-row" key={index}>
          {onSelect ? (
            <button
              className="ghost bar-label"
              onClick={() => onSelect(item.value)}
            >
              {String(item.value)}
            </button>
          ) : (
            <span className="bar-label">{String(item.value)}</span>
          )}
          <progress
            style={
              { "--bar-color": colors?.[String(item.value)] } as CSSProperties
            }
            value={item.count}
            max={total || 1}
            aria-label={`${String(item.value)}: ${item.count}`}
          />
          <span className="bar-value">{item.count}</span>
        </div>
      ))}
    </div>
  );
}
export function ResourceState({ error }: { error?: Error | null }) {
  return (
    <Card title={error ? "Could not load this view" : "Loading…"}>
      <p role={error ? "alert" : "status"}>
        {error?.message || "Reading your local project."}
      </p>
    </Card>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function ProviderFields({
  backend,
  model,
  onBackend,
  onModel,
}: {
  backend: Backend;
  model: string;
  onBackend: (value: Backend) => void;
  onModel: (value: string) => void;
}) {
  return (
    <div className="row">
      <Choice
        label="Analyzer"
        options={["codex", "claude"]}
        value={backend}
        onChange={onBackend}
      />
      <Field
        label="Model (optional; CLI default)"
        value={model}
        onChange={onModel}
      />
    </div>
  );
}
export function ActionButton({
  action,
  children,
  className = "",
  onSuccess,
}: {
  action: () => Promise<unknown>;
  children: ReactNode;
  className?: string;
  onSuccess?: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const client = useQueryClient();
  async function run() {
    setPending(true);
    setError("");
    try {
      await action();
      await client.invalidateQueries();
      onSuccess?.();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Operation failed");
    } finally {
      setPending(false);
    }
  }
  return (
    <span className="action">
      <button
        type="button"
        disabled={pending}
        className={className}
        onClick={() => void run()}
      >
        {pending ? "Working…" : children}
      </button>
      {error && (
        <span className="error-text" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
export function submit(action: () => void) {
  return (event: FormEvent) => {
    event.preventDefault();
    action();
  };
}
