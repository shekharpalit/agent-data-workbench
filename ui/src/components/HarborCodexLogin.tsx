export function HarborCodexLogin({
  agent,
  checked,
  onChange,
  label = "Use host Codex login",
}: {
  agent: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  label?: string;
}) {
  if (agent.trim() !== "codex") return null;
  return (
    <div>
      <label className="row">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        {label}
      </label>
      <p className="muted">
        Harbor passes the server user's existing ~/.codex/auth.json login into
        the task container. Use this only with environments and agents you
        trust. Credential contents are not stored in the workbench
        configuration.
      </p>
    </div>
  );
}
