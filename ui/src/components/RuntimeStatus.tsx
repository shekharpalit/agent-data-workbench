import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Badge, Details } from "./shared";

export function RuntimeStatus({
  tools = ["codex", "claude"],
}: {
  tools?: string[];
}) {
  const request = useQuery({
    queryKey: ["runtime"],
    queryFn: ({ signal }) => api.runtime(signal),
    staleTime: 60000,
    retry: false,
  });
  return (
    <div className="runtime-status">
      <div className="row">
        <h3>Runtime setup</h3>
        <button
          className="ghost"
          disabled={request.isFetching}
          onClick={() => void request.refetch()}
        >
          {request.isFetching ? "Checking…" : "Check setup"}
        </button>
      </div>
      {request.error && <p className="error-text">{request.error.message}</p>}
      {request.data && (
        <>
          {request.data.tools
            .filter((tool) => tools.includes(tool.name))
            .map((tool) => (
              <div className="item" key={tool.name}>
                <strong>{tool.name}</strong>{" "}
                <Badge
                  value={
                    tool.ready
                      ? "ready"
                      : tool.installed
                        ? tool.authentication === "login_required"
                          ? "login_required"
                          : "check_required"
                        : "not_installed"
                  }
                />
                <p className="muted">
                  {tool.version ||
                    "Install this CLI where the workbench backend runs."}
                </p>
                {tool.authentication === "login_required" && (
                  <pre>
                    {tool.name === "codex"
                      ? "codex login"
                      : "claude auth login"}
                  </pre>
                )}
                {tool.executable && (
                  <Details title={`${tool.name} executable`}>
                    <code>{tool.executable}</code>
                  </Details>
                )}
              </div>
            ))}
          {request.data.environment === "container" && (
            <p className="scope-note">
              This backend runs in Docker. Host CLI logins are not available
              inside it. To use your native Claude/Codex session and local
              Harbor Docker runtime, run <code>make init MODE=native</code> then{" "}
              <code>make dev MODE=native PORT=8766</code>.
            </p>
          )}
          <p className="muted">
            Ready confirms CLI availability and login status where applicable.
            Model access and provider limits are checked by the actual session.
          </p>
        </>
      )}
    </div>
  );
}
