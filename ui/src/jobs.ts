import type { Job, Route } from "./contracts";

export function jobDestination(job: Job): Route | null {
  const result = job.result;
  if (!result || typeof result.id !== "string") return null;
  if (result.kind === "huggingface") return { view: "imports" };
  if (Array.isArray(result.trials))
    return { view: "experiments", id: result.id };
  if (job.name.startsWith("Investigate "))
    return { view: "investigations", id: result.id };
  return null;
}
