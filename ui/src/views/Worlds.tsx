import { useState } from "react";
import { api } from "../api";
import type { World, WorldSpec } from "../workflow-contracts";
import {
  ActionButton,
  Badge,
  Card,
  Details,
  Field,
  JsonView,
  ResourceState,
} from "../components/shared";
import {
  jsonObject,
  lines,
  useWorkflow,
  VersionReview,
} from "./WorkflowShared";

const emptyWorld: WorldSpec = {
  name: "",
  domain: "",
  description: "",
  schemas: {},
  tools: [],
  relationships: [],
  permissions: [],
  invariants: [],
  sources: [],
  unresolved_questions: [],
};
export function WorldEditor({
  previous,
  onSaved,
}: {
  previous?: World;
  onSaved: (id: string) => void;
}) {
  const [spec, setSpec] = useState<WorldSpec>(previous?.spec ?? emptyWorld);
  const [schemas, setSchemas] = useState(JSON.stringify(spec.schemas, null, 2));
  const [tools, setTools] = useState(
    spec.tools.map((tool) => ({
      ...tool,
      input: JSON.stringify(tool.input_schema, null, 2),
      output: JSON.stringify(tool.output_schema, null, 2),
    })),
  );
  function update<K extends keyof WorldSpec>(key: K, value: WorldSpec[K]) {
    setSpec((s) => ({ ...s, [key]: value }));
  }
  return (
    <Card
      title={
        previous ? `Revise ${previous.spec.name}` : "Define a reusable world"
      }
    >
      <p className="muted">
        Record domain rules and tool contracts shared by tasks. Each saved
        version is reviewed separately.
      </p>
      <div className="stack">
        <div className="row">
          <Field
            label="World name"
            value={spec.name}
            onChange={(v) => update("name", v)}
          />
          <Field
            label="Domain"
            value={spec.domain}
            onChange={(v) => update("domain", v)}
          />
        </div>
        <Field
          label="World description"
          value={spec.description}
          onChange={(v) => update("description", v)}
          multiline
        />
        {(
          [
            ["relationships", "Relationships"],
            ["permissions", "Permissions"],
            ["invariants", "Success invariants"],
            ["sources", "Source references"],
            ["unresolved_questions", "Unresolved questions"],
          ] as const
        ).map(([key, label]) => (
          <Field
            key={key}
            label={`${label} (one per line)`}
            value={spec[key].join("\n")}
            onChange={(v) => update(key, v.split("\n"))}
            multiline
          />
        ))}
        <Details title="Schemas and tool contracts">
          <Field
            label="Named schemas JSON"
            value={schemas}
            onChange={setSchemas}
            multiline
          />
          {tools.map((tool, index) => (
            <fieldset key={index} className="stack">
              <legend>Tool {index + 1}</legend>
              {(
                [
                  ["name", "Tool name"],
                  ["description", "Tool description"],
                  ["input", "Input schema JSON"],
                  ["output", "Output schema JSON"],
                ] as const
              ).map(([key, label]) => (
                <Field
                  key={key}
                  label={`${label} ${index + 1}`}
                  multiline={key !== "name"}
                  value={tool[key]}
                  onChange={(value) =>
                    setTools((items) =>
                      items.map((item, i) =>
                        i === index ? { ...item, [key]: value } : item,
                      ),
                    )
                  }
                />
              ))}
              <button
                className="danger"
                onClick={() =>
                  setTools((items) => items.filter((_, i) => i !== index))
                }
              >
                Remove tool {index + 1}
              </button>
            </fieldset>
          ))}
          <button
            className="secondary"
            onClick={() =>
              setTools((items) => [
                ...items,
                {
                  name: "",
                  description: "",
                  input_schema: {},
                  output_schema: {},
                  input: "{}",
                  output: "{}",
                },
              ])
            }
          >
            Add tool
          </button>
        </Details>
        <ActionButton
          action={async () => {
            if (
              !spec.name.trim() ||
              !spec.domain.trim() ||
              !spec.description.trim() ||
              !lines(spec.sources.join("\n")).length
            )
              throw new Error(
                "Enter a name, domain, description and source reference.",
              );
            const parsed = jsonObject(schemas, "Named schemas");
            for (const value of Object.values(parsed))
              if (!value || typeof value !== "object" || Array.isArray(value))
                throw new Error("Every named schema must be a JSON object.");
            const saved = await api.createWorld(
              {
                ...spec,
                schemas: parsed as WorldSpec["schemas"],
                tools: tools.map((tool) => ({
                  name: tool.name,
                  description: tool.description,
                  input_schema: jsonObject(tool.input, "Input schema"),
                  output_schema: jsonObject(tool.output, "Output schema"),
                })),
                relationships: lines(spec.relationships.join("\n")),
                permissions: lines(spec.permissions.join("\n")),
                invariants: lines(spec.invariants.join("\n")),
                sources: lines(spec.sources.join("\n")),
                unresolved_questions: lines(
                  spec.unresolved_questions.join("\n"),
                ),
              },
              previous?.id,
            );
            onSaved(saved.id);
          }}
        >
          Save world draft
        </ActionButton>
      </div>
    </Card>
  );
}
export function WorldsView() {
  const request = useWorkflow();
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState(false);
  if (!request.data) return <ResourceState error={request.error} />;
  const world = request.data.worlds.find((w) => w.id === selected);
  return (
    <>
      <Card title="World specifications">
        <p>
          Reviewed knowledge about your domain, schemas, tools and permissions.
          Tasks pin a specific accepted version.
        </p>
        <div className="workflow-library">
          {request.data.worlds.map((item) => (
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
              <strong>{item.spec.name}</strong>
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
          Create world
        </button>
      </Card>
      {world && !editing ? (
        <>
          <Card title={world.spec.name}>
            <div className="pill-group">
              <Badge value={world.review.status} />
              <Badge value={world.spec.domain} />
            </div>
            <p>{world.spec.description}</p>
            <p>
              Version {world.revision} · <code>{world.id}</code>
            </p>
            <Details title="Reviewed domain and tool specification">
              <JsonView value={world.spec} />
            </Details>
            <Details title="Task reference">
              <JsonView value={{ id: world.id, sha256: world.sha256 }} />
            </Details>
            {world.spec.unresolved_questions.length > 0 && (
              <p className="scope-note">
                Resolve {world.spec.unresolved_questions.length} open questions
                in a new version before acceptance.
              </p>
            )}
            <button className="secondary" onClick={() => setEditing(true)}>
              Create next version
            </button>
          </Card>
          <Card title="Review this exact world version">
            <VersionReview
              key={world.id}
              review={(status, note, reviewer) =>
                api.reviewWorld(world.id, status, note, reviewer)
              }
            />
          </Card>
        </>
      ) : (
        <WorldEditor
          key={world?.id || "new"}
          previous={world}
          onSaved={(id) => {
            setSelected(id);
            setEditing(false);
          }}
        />
      )}
    </>
  );
}
