"""Typed configuration for the local FastAPI application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Mapping

from pydantic import Field, HttpUrl, field_validator
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSettings:
    project: Path
    host: Annotated[str, Field(min_length=1)]
    port: Annotated[int, Field(ge=1, le=65535)]
    origin: str
    name: str
    objective: str

    @field_validator("origin")
    @classmethod
    def browser_origin(cls, value: str) -> str:
        url = HttpUrl(value)
        if (
            url.username is not None
            or url.password is not None
            or url.path not in {None, "/"}
            or url.query is not None
            or url.fragment is not None
            or url.port == 0
            or "*" in url.host
            or url.host == "0.0.0.0"
        ):
            raise ValueError("Use a browser origin without credentials, a path, query or fragment")
        if "[" in url.host:
            # TrustedHostMiddleware matches hostnames and IPv4 literals.
            raise ValueError("Use an IPv4 address or hostname for the browser origin")
        return str(url).rstrip("/")

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> RuntimeSettings:
        values = os.environ if environment is None else environment
        root = values.get("WORKBENCH_PROJECT", "runs/workbench")
        if not root.strip():
            raise ValueError("WORKBENCH_PROJECT must name a directory")
        port = values.get("WORKBENCH_PORT", "8765")
        return cls(
            project=Path(root).expanduser().resolve(),
            host=values.get("WORKBENCH_HOST", "127.0.0.1").strip(),
            port=port,
            origin=values.get("WORKBENCH_ORIGIN", f"http://127.0.0.1:{port}"),
            name=values.get("WORKBENCH_NAME", "Agent Data Workbench"),
            objective=values.get(
                "WORKBENCH_OBJECTIVE", "Investigate agent traces and evaluate improvements"
            ),
        )
