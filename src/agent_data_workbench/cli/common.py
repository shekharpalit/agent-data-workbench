"""Shared CLI output and error handling."""

import json
from functools import wraps
from pathlib import Path

import typer
from pydantic import ValidationError

from agent_data_workbench.execution.contracts import RunnerConfig
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.shared.json import read_json
from agent_data_workbench.shared.processes import BackendError


def errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValidationError as exc:
            fields = [".".join(map(str, error["loc"])) for error in exc.errors(include_input=False)]
            typer.echo("Invalid structured data at: " + ", ".join(fields[:10]), err=True)
            raise typer.Exit(2) from exc
        except (ValueError, OSError, BackendError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(2) from exc

    return wrapped


def emit(value):
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def runner(path: Path):
    return ConfiguredRunner(RunnerConfig.model_validate(read_json(path)), path.parent)
