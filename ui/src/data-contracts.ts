import type { Json } from "./contracts";

export interface DatasetImport {
  dataset: string;
  configuration: string | null;
  split: string;
  revision: string;
  id_pointer: string;
  group_pointer: string;
  stratum_pointer: string;
  limit: number | null;
}
export interface DatasetSource {
  provider: string;
  dataset: string;
  revision: string;
  configuration: string;
  split: string;
  url: string;
  license: Json;
  features: Record<string, Json>;
  selection: { limit: number | null; order: string };
}
export interface ImportReceipt {
  id: string;
  created_at: string;
  status: string;
  source: DatasetSource;
  config: DatasetImport;
  result: { added: number; unchanged: number; total: number } | null;
  error: string | null;
}
export interface DatasetGroup {
  id: string;
  label: string;
  strata: string[];
  count: number;
  trace_ids: string[];
  outcomes: Record<"Passed" | "Failed" | "Unknown", number>;
}
export interface DatasetProfile {
  eligible: number;
  group_count: number;
  groups: DatasetGroup[];
  outcome_pointer: string;
  outcomes: { value: string; count: number }[];
  scope: string;
}
