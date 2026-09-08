import json
import sys
from pathlib import Path

import pytest

from agent_data_workbench.integrations.analyzers import CliAnalyzer
from agent_data_workbench.shared.processes import BackendError, run_process


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_provider_adapters_use_structured_output_and_native_auth(monkeypatch, analysis, backend):
    # Given
    monkeypatch.setattr(
        "agent_data_workbench.integrations.analyzers.shutil.which", lambda name: "/usr/bin/" + name
    )
    observed = {}

    def fake_run(args, prompt, cwd, timeout):
        observed.update(prompt=prompt, timeout=timeout, model=args[args.index("--model") + 1])
        if backend == "codex":
            observed.update(
                sandbox=args[args.index("--sandbox") + 1],
                ignore_user_config="--ignore-user-config" in args,
            )
            path = Path(args[args.index("--output-last-message") + 1])
            schema_path = Path(args[args.index("--output-schema") + 1])
            observed["schema"] = json.loads(schema_path.read_text())
            path.write_text(analysis.model_dump_json())
            return ""
        observed.update(
            safe_mode="--safe-mode" in args,
            bare="--bare" in args,
            tools=args[args.index("--tools") + 1],
        )
        return json.dumps({"is_error": False, "structured_output": analysis.model_dump()})

    monkeypatch.setattr("agent_data_workbench.integrations.analyzers.run_process", fake_run)

    # When
    actual = CliAnalyzer(backend, model="explicit-model", timeout=37).analyze(
        "input-data", {"type": "object"}
    )

    # Then
    assert actual == analysis.model_dump()
    expected = {"prompt": "input-data", "timeout": 37, "model": "explicit-model"}
    expected.update(
        {"sandbox": "read-only", "ignore_user_config": True, "schema": {"type": "object"}}
        if backend == "codex"
        else {"safe_mode": True, "bare": False, "tools": ""}
    )
    assert observed == expected


def test_missing_cli_is_actionable(monkeypatch):
    # Given
    monkeypatch.setattr(
        "agent_data_workbench.integrations.analyzers.shutil.which", lambda name: None
    )

    # When / Then
    with pytest.raises(BackendError, match="not installed"):
        CliAnalyzer("codex").analyze("data", {})


def test_provider_error_envelope_is_not_analysis(monkeypatch):
    # Given
    monkeypatch.setattr(
        "agent_data_workbench.integrations.analyzers.shutil.which", lambda name: name
    )
    monkeypatch.setattr(
        "agent_data_workbench.integrations.analyzers.run_process",
        lambda *args: json.dumps({"is_error": True, "result": "sensitive account details"}),
    )

    # When / Then
    with pytest.raises(BackendError, match="did not complete"):
        CliAnalyzer("claude").analyze("data", {})


def test_subprocess_receives_literal_stdin(tmp_path):
    # Given
    prompt = "literal $(never-run-this) and backticks"

    # When
    actual = run_process(
        [sys.executable, "-c", "import sys; print(sys.stdin.read())"], prompt, tmp_path, 5
    )

    # Then
    assert {"stdout": actual.strip()} == {"stdout": "literal $(never-run-this) and backticks"}


def test_subprocess_errors_do_not_echo_private_stderr(tmp_path):
    # Given
    args = [
        sys.executable,
        "-c",
        "import sys; print('private trace text',file=sys.stderr); sys.exit(3)",
    ]

    # When
    with pytest.raises(BackendError) as caught:
        run_process(args, "", tmp_path, 5)

    # Then
    assert {
        "has_private_text": "private trace" in str(caught.value),
        "has_exit_code": "code 3" in str(caught.value),
    } == {
        "has_private_text": False,
        "has_exit_code": True,
    }


def test_timeout_terminates_local_process(tmp_path):
    # Given
    args = [sys.executable, "-c", "import time; time.sleep(30)"]

    # When / Then
    with pytest.raises(BackendError, match="timed out"):
        run_process(args, "", tmp_path, 1)
