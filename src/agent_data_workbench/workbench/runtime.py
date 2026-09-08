"""Launch the FastAPI app through Uvicorn for native and container use."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from agent_data_workbench.api import create_app
from agent_data_workbench.workbench.settings import RuntimeSettings as RuntimeSettings
from agent_data_workbench.workspace.project import Project

SESSION_TOKEN_ENV = "_WORKBENCH_SESSION_TOKEN"


def initialize_project(settings: RuntimeSettings) -> Project:
    """Create an empty workspace once; validate and retain every existing artifact."""
    root = settings.project
    if (root / "project.json").is_file():
        return Project(root)
    return Project.create(root, settings.name, settings.objective)


def create_application() -> FastAPI:
    """Application factory shared by Uvicorn's regular and reload modes."""
    settings = RuntimeSettings.from_env()
    token = os.environ.setdefault(SESSION_TOKEN_ENV, secrets.token_urlsafe(32))
    return create_app(initialize_project(settings), origin=settings.origin, token=token)


def launch(settings: RuntimeSettings, *, reload: bool = False) -> None:
    # The factory and reload child read the same project configuration and session.
    os.environ.update(
        WORKBENCH_PROJECT=str(settings.project),
        WORKBENCH_HOST=settings.host,
        WORKBENCH_PORT=str(settings.port),
        WORKBENCH_ORIGIN=settings.origin,
        WORKBENCH_NAME=settings.name,
        WORKBENCH_OBJECTIVE=settings.objective,
    )
    token = secrets.token_urlsafe(32)
    os.environ[SESSION_TOKEN_ENV] = token
    print(f"Local workbench: {settings.origin}/#token={token}", flush=True)
    print("Open this private URL after Uvicorn reports startup. Press Ctrl-C to stop.", flush=True)
    uvicorn.run(
        "agent_data_workbench.workbench.runtime:create_application",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=reload,
        reload_dirs=[str(Path(__file__).resolve().parent.parent)] if reload else None,
        access_log=False,
        proxy_headers=False,
        server_header=False,
        ws="none",
    )


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
    if not args.initialize_only:
        launch(settings, reload=args.reload)


if __name__ == "__main__":
    main()
