import { expect, it } from "vitest";
import { jobDestination } from "../src/jobs";

it("Given completed jobs, When opening results, Then resolves only existing artifact destinations", () => {
  // Given
  const base = { id: "job", status: "complete" as const, error: null };
  const jobs = [
    {
      ...base,
      name: "Import Hugging Face dataset",
      result: { id: "import", kind: "huggingface" },
    },
    {
      ...base,
      name: "Run Harbor comparison",
      result: { id: "experiment", trials: [] },
    },
    {
      ...base,
      name: "Run exported Harbor task",
      result: { id: "run", export_id: "export" },
    },
    {
      ...base,
      name: "Investigate project",
      result: { id: "investigation", status: "paused" },
    },
  ];
  // When / Then
  expect(jobs.map(jobDestination)).toStrictEqual([
    { view: "imports" },
    { view: "experiments", id: "experiment" },
    null,
    { view: "investigations", id: "investigation" },
  ]);
});
