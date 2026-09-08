"""Configurable local and container entrypoint for the FastAPI workbench."""

from __future__ import annotations

import argparse
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import uvicorn
from fastapi import FastAPI

from agent_data_workbench.api import create_app
from agent_data_workbench.workbench.server import WorkbenchServer, validate_origin
from agent_data_workbench.workspace.project import Project

SESSION_TOKEN_ENV = "_WORKBENCH_SESSION_TOKEN"


@dataclass(frozen=True)
class RuntimeSettings:
    project: Path
    host: str
    port: int
    origin: str
    name: str
    objective: str

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> RuntimeSettings:
        values = os.environ if environment is None else environment
        try:
            port = int(values.get("WORKBENCH_PORT", "8765"))
        except ValueError as exc:
            raise ValueError("WORKBENCH_PORT must be an integer from 1 to 65535") from exc
        if not 1 <= port <= 65535:
            raise ValueError("WORKBENCH_PORT must be an integer from 1 to 65535")
        host = values.get("WORKBENCH_HOST", "127.0.0.1").strip()
        if not host or any(character.isspace() for character in host):
            raise ValueError("WORKBENCH_HOST must be a bind address or hostname")
        root = values.get("WORKBENCH_PROJECT", "runs/workbench")
        if not root.strip():
            raise ValueError("WORKBENCH_PROJECT must name a directory")
        return cls(
            project=Path(root).expanduser().resolve(),
            host=host,
            port=port,
            origin=validate_origin(values.get("WORKBENCH_ORIGIN", f"http://127.0.0.1:{port}")),
            name=values.get("WORKBENCH_NAME", "Agent Data Workbench"),
            objective=values.get(
                "WORKBENCH_OBJECTIVE", "Investigate agent traces and evaluate improvements"
            ),
        )


def initialize_project(settings: RuntimeSettings) -> Project:
    """Create an empty workspace once; validate and retain every existing artifact."""
    root = settings.project
    if (root / "project.json").is_file():
        return Project(root)
    return Project.create(root, settings.name, settings.objective)


def create_application() -> FastAPI:
    """Import-string factory used by Uvicorn's reload child process."""
    settings = RuntimeSettings.from_env()
    token = os.environ.setdefault(SESSION_TOKEN_ENV, secrets.token_urlsafe(32))
    return create_app(initialize_project(settings), origin=settings.origin, token=token)


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--initialize-only", action="store_true", help="Create or validate the workspace and exit"
    )
    parser.add_argument("--reload", action="store_true", help="Restart after Python source changes")
    args = parser.parse_args(arguments)
    try:
        settings = RuntimeSettings.from_env()
        project = initialize_project(settings)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot start workbench: {exc}\n")
    print(f"Workbench project: {project.root}", flush=True)
    if args.initialize_only:
        return

    token = secrets.token_urlsafe(32)
    print(f"Local workbench: {settings.origin}/#token={token}", flush=True)
    print("Keep this URL private. Press Ctrl-C to stop.", flush=True)
    if args.reload:
        # Uvicorn's spawned child inherits this session; edits must not invalidate browser access.
        os.environ[SESSION_TOKEN_ENV] = token
        uvicorn.run(
            "agent_data_workbench.workbench.runtime:create_application",
            factory=True,
            host=settings.host,
            port=settings.port,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parent.parent)],
            access_log=False,
            log_level="info",
            proxy_headers=False,
            server_header=False,
            ws="none",
        )
    else:
        server = WorkbenchServer(
            project,
            settings.port,
            host=settings.host,
            public_origin=settings.origin,
            token=token,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
