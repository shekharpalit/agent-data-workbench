import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Route } from "../contracts";
import type {
  BehavioralCoverage,
  Capability,
  Taxonomy,
  TaxonomySpec,
} from "../workflow-contracts";
import {
  ActionButton,
  Badge,
  Card,
  Choice,
  Details,
  Field,
  JsonView,
  ResourceState,
  Table,
} from "../components/shared";
import {
  lines,
  SelectField,
  useWorkflow,
  VersionReview,
} from "./WorkflowShared";

export function TaxonomyEditor({
  previous,
  onSaved,
}: {
  previous?: Taxonomy;
  onSaved: (id: string) => void;
}) {
  const [name, setName] = useState(previous?.spec.name || "");
  const [description, setDescription] = useState(
    previous?.spec.description || "",
  );
  const [capabilities, setCapabilities] = useState<Capability[]>(
    previous?.spec.capabilities || [],
  );
  function update(
    index: number,
    key: keyof Capability,
    value: string | string[],
  ) {
    setCapabilities((items) =>
      items.map((item, i) => (i === index ? { ...item, [key]: value } : item)),
    );
  }
  return (
    <Card
      title={
        previous
          ? `New version of ${previous.spec.name}`
          : "Define behavioral coverage"
      }
    >
      <p className="muted">
        Name the capabilities your agent needs and the situations each must
        handle. Coverage comes from explicit trace and task mappings.
      </p>
      <div className="stack">
        <Field label="Taxonomy name" value={name} onChange={setName} />
        <Field
          label="Taxonomy description"
          value={description}
          onChange={setDescription}
          multiline
        />
        {capabilities.map((item, index) => (
          <fieldset key={item.id} className="stack">
            <legend>Capability {index + 1}</legend>
            <Field
              label={`Capability name ${index + 1}`}
              value={item.name}
              onChange={(v) => update(index, "name", v)}
            />
            <Field
              label={`Capability description ${index + 1}`}
              value={item.description}
              onChange={(v) => update(index, "description", v)}
              multiline
            />
            <Field
              label={`Required slices ${index + 1} (one per line)`}
              value={item.required_slices.join("\n")}
              onChange={(v) => update(index, "required_slices", v.split("\n"))}
              multiline
            />
            <button
              className="danger"
              onClick={() =>
                setCapabilities((items) => items.filter((_, i) => i !== index))
              }
            >
              Remove capability {index + 1}
            </button>
          </fieldset>
        ))}
        <button
          className="secondary"
          onClick={() =>
            setCapabilities((items) => [
              ...items,
              {
                id: crypto.randomUUID(),
                name: "",
                description: "",
                required_slices: [],
              },
            ])
          }
        >
          Add capability
        </button>
        <ActionButton
          action={async () => {
            if (
              !name.trim() ||
              !capabilities.length ||
              capabilities.some((c) => !c.name.trim() || !c.description.trim())
            )
              throw new Error(
                "Name the taxonomy and add at least one named, described capability.",
              );
            const spec: TaxonomySpec = {
              name,
              description,
              capabilities: capabilities.map((c) => ({
                ...c,
                required_slices: lines(c.required_slices.join("\n")),
              })),
            };
            const saved = await api.createTaxonomy(spec, previous?.id);
            onSaved(saved.id);
          }}
        >
          Save taxonomy draft
        </ActionButton>
      </div>
    </Card>
  );
}
export function CoverageMapEditor({ taxonomy }: { taxonomy: Taxonomy }) {
  const [kind, setKind] = useState<"trace" | "task">("trace");
  const [entity, setEntity] = useState("");
  const [capability, setCapability] = useState("");
  const [slice, setSlice] = useState("");
  const [rationale, setRationale] = useState("");
  const [source, setSource] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [saved, setSaved] = useState(false);
  const selected = taxonomy.spec.capabilities.find((c) => c.id === capability);
  return (
    <Card title="Map observed behavior">
      <p>
        Map an existing trace or task version to an accepted capability. The
        mapping retains the source evidence and reviewer.
      </p>
      <div className="stack">
        <div className="row">
          <Choice
            label="Evidence kind"
            value={kind}
            options={["trace", "task"]}
            onChange={setKind}
          />
          <Field
            label={kind === "trace" ? "External trace ID" : "Task ID"}
            value={entity}
            onChange={setEntity}
          />
        </div>
        <SelectField
          label="Capability"
          value={capability}
          onChange={(v) => {
            setCapability(v);
            setSlice("");
          }}
          options={taxonomy.spec.capabilities.map((c) => ({
            id: c.id,
            label: c.name,
          }))}
        />
        <SelectField
          label="Behavioral slice"
          value={slice}
          onChange={setSlice}
          placeholder="Capability overall"
          options={(selected?.required_slices || []).map((s) => ({
            id: s,
            label: s,
          }))}
        />
        <Field
          label="Mapping rationale"
          value={rationale}
          onChange={setRationale}
          multiline
        />
        <Field
          label="Evidence source reference"
          value={source}
          onChange={setSource}
        />
        <Field
          label="Mapping reviewer"
          value={reviewer}
          onChange={setReviewer}
        />
        <ActionButton
          action={async () => {
            if (
              !entity.trim() ||
              !capability ||
              !rationale.trim() ||
              !source.trim() ||
              !reviewer.trim()
            )
              throw new Error(
                "Select a capability and provide the entity, rationale, source and reviewer.",
              );
            await api.mapCoverage(taxonomy.id, {
              kind,
              entity_id: entity,
              capability_id: capability,
              slice,
              rationale,
              source,
              reviewer,
            });
            setSaved(true);
          }}
        >
          Save evidence mapping
        </ActionButton>
        {saved && (
          <p role="status">
            Mapping saved for this taxonomy and exact source version.
          </p>
        )}
      </div>
    </Card>
  );
}
export function CoverageReport({
  report,
  navigate,
}: {
  report: BehavioralCoverage;
  navigate: (route: Route) => void;
}) {
  return (
    <>
      <Card title="Behavioral coverage">
        <p className="scope-note">{report.scope}</p>
        <Table
          headings={[
            "Capability",
            "Traces / groups",
            "Accepted tasks",
            "Executed versions",
            "Pass / fail / invalid",
            "Missing accepted slices",
          ]}
          rows={report.capabilities.map((c) => ({
            key: c.id,
            cells: [
              c.name,
              `${c.traces} / ${c.independent_trace_groups}`,
              c.accepted_tasks,
              `${c.tested_task_versions} / ${c.task_versions}`,
              `${c.trial_results.pass} / ${c.trial_results.fail} / ${c.trial_results.invalid}`,
              c.missing_accepted_slices.join(", ") || "—",
            ],
          }))}
        />
      </Card>
      {report.capabilities.map((c) => (
        <Card title={c.name} key={c.id}>
          <p>
            {c.unexecuted_task_versions} task versions not executed ·{" "}
            {c.unexecuted_slices.length} unexecuted required slices
          </p>
          {c.all_observed_valid_attempts_passed && (
            <p className="scope-note">
              All observed valid attempts passed. Review fresh cases and task
              diversity before deciding this behavior is sufficiently tested.
            </p>
          )}
          <div className="coverage-slices">
            {c.required_slices.map((slice) => (
              <div className="coverage-slice" key={slice.name}>
                <strong>{slice.name}</strong>
                <Badge
                  value={
                    !slice.accepted_tasks
                      ? "missing"
                      : !slice.tested_task_versions
                        ? "pending"
                        : "tested"
                  }
                />
                <span>
                  {slice.traces} traces · {slice.accepted_tasks} accepted tasks
                  · {slice.tested_task_versions} executed versions
                </span>
              </div>
            ))}
          </div>
        </Card>
      ))}
      <div className="grid two">
        <Card title="Unmapped evidence">
          <p>
            {report.unmapped_trace_ids.length} traces ·{" "}
            {report.unmapped_task_ids.length} tasks
          </p>
          <Details title="Unmapped traces">
            {report.unmapped_trace_ids.map((id) => (
              <p key={id}>
                <button
                  className="ghost"
                  onClick={() => navigate({ view: "traces", id })}
                >
                  {id}
                </button>
              </p>
            ))}
          </Details>
          <Details title="Unmapped tasks">
            {report.unmapped_task_ids.map((id) => (
              <p key={id}>
                <button
                  className="ghost"
                  onClick={() => navigate({ view: "tasks", id })}
                >
                  {id}
                </button>
              </p>
            ))}
          </Details>
        </Card>
        <Card title="Duplicates and changed tasks">
          <p>
            {report.duplicate_groups.length} duplicate content groups ·{" "}
            {report.stale_mapping_ids.length} stale mappings
          </p>
          <Details title="Inspect duplicate groups and stale mappings">
            <JsonView
              value={{
                duplicates: report.duplicate_groups,
                stale_mapping_ids: report.stale_mapping_ids,
              }}
            />
          </Details>
        </Card>
      </div>
    </>
  );
}
function TaxonomyDetail({
  taxonomy,
  navigate,
  onRevise,
}: {
  taxonomy: Taxonomy;
  navigate: (route: Route) => void;
  onRevise: () => void;
}) {
  const report = useQuery({
    queryKey: ["behavioral-coverage", taxonomy.id],
    queryFn: ({ signal }) => api.behavioralCoverage(taxonomy.id, signal),
  });
  return (
    <>
      <Card title={taxonomy.spec.name}>
        <Badge value={taxonomy.review.status} />
        <p>{taxonomy.spec.description}</p>
        <p>
          Version {taxonomy.revision} · <code>{taxonomy.id}</code>
        </p>
        <button className="secondary" onClick={onRevise}>
          Create next taxonomy version
        </button>
        <Details title="Taxonomy specification">
          <JsonView value={taxonomy.spec} />
        </Details>
        <Details title="Review this taxonomy version">
          <VersionReview
            key={taxonomy.id}
            review={(status, note, reviewer) =>
              api.reviewTaxonomy(taxonomy.id, status, note, reviewer)
            }
          />
        </Details>
      </Card>
      {report.data ? (
        <CoverageReport report={report.data} navigate={navigate} />
      ) : (
        <ResourceState error={report.error} />
      )}{" "}
      {taxonomy.review.status === "accepted" ? (
        <CoverageMapEditor key={taxonomy.id} taxonomy={taxonomy} />
      ) : (
        <p className="scope-note">
          Accept this taxonomy version to classify evidence.
        </p>
      )}
    </>
  );
}
export function BehavioralCoverageView({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const request = useWorkflow();
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState(false);
  if (!request.data) return <ResourceState error={request.error} />;
  const taxonomy = request.data.taxonomies.find((t) => t.id === selected);
  return (
    <>
      <Card title="Behavior taxonomies">
        <p>
          Compare the behaviors represented in production evidence, reviewed
          tasks, and actual eval runs.
        </p>
        <div className="workflow-library">
          {request.data.taxonomies.map((item) => (
            <button
              key={item.id}
              className={
                selected === item.id ? "selected-artifact" : "secondary"
              }
              onClick={() => {
                setSelected(item.id);
                setEditing(false);
              }}
            >
              {item.spec.name}
              <span>
                Version {item.revision} · {item.review.status}
              </span>
            </button>
          ))}
        </div>
        <button
          className="ghost"
          onClick={() => {
            setSelected("");
            setEditing(true);
          }}
        >
          Create taxonomy
        </button>
      </Card>
      {taxonomy && !editing ? (
        <TaxonomyDetail
          taxonomy={taxonomy}
          navigate={navigate}
          onRevise={() => setEditing(true)}
        />
      ) : (
        <TaxonomyEditor
          key={taxonomy?.id || "new"}
          previous={taxonomy}
          onSaved={(id) => {
            setSelected(id);
            setEditing(false);
          }}
        />
      )}
    </>
  );
}
