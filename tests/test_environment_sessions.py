import json
import sys
from pathlib import Path

import pytest

from agent_data_workbench.execution.artifacts import read_artifacts
from agent_data_workbench.execution.contracts import (
    ConversationSpec,
    EnvironmentConfig,
    RunnerConfig,
    SimulatorConfig,
    UserTurn,
)
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.shared.json import digest

ENVIRONMENT_SCRIPT = """
import json,sys
from pathlib import Path
request=json.load(sys.stdin)
phase=request['phase']
state=Path(request['state_dir'])/'database.json'
if phase=='setup':
    result={'target_context':{'database':str(state)}}
elif phase=='reset':
    state.write_text(json.dumps({'subscription':'active','changes':0}))
    result={'reset':True}
elif phase=='ready':
    result={'ready':state.exists()}
elif phase=='inspect':
    result={'artifacts':{'state.json':json.loads(state.read_text())}}
else:
    result={'stopped':True}
print(json.dumps(result))
"""
SESSION_SCRIPT = """
import json,sys
from pathlib import Path
history=[]
initial=None
for line in sys.stdin:
    request=json.loads(line)
    if initial is None:
        initial=request['input']
    history.append(request['message'])
    if request['message']=='Confirm cancellation':
        database=Path(initial['environment_context']['database'])
        database.write_text(json.dumps({'subscription':'cancelled','changes':1}))
    # A target may claim fabricated state, but cannot populate the observer channel.
    Path('state.json').write_text(json.dumps({'subscription':'claimed','changes':999}))
    print(json.dumps({'message':'Recorded', 'output':{'messages':history.copy()},
                      'evidence':[{'tool':'subscription_service','turn':request['turn_index']}]}),
          flush=True)
"""


def configured(tmp_path, *, script=SESSION_SCRIPT, environment=True, turns=None, timeout=3):
    (tmp_path / "environment.py").write_text(ENVIRONMENT_SCRIPT)
    (tmp_path / "target.py").write_text(script)
    command = [sys.executable, "environment.py"]
    env = EnvironmentConfig(
        name="subscriptions",
        version="fixture-v1",
        authority="fixture subscription database",
        setup=command,
        reset=command,
        ready=command,
        inspect=command,
        teardown=command,
        initial_state_sha256=digest({"state.json": {"subscription": "active", "changes": 0}}),
    )
    runner = ConfiguredRunner(
        RunnerConfig(
            name="support",
            kind="command",
            command=[sys.executable, "target.py"],
            environment_version="fixture-v1",
            fidelity="environment" if environment else "output",
            environment=env if environment else None,
            conversation=ConversationSpec(
                turns=turns
                or [
                    UserTurn(message="Cancel subscription"),
                    UserTurn(message="Confirm cancellation"),
                ]
            ),
            timeout=timeout,
        ),
        tmp_path,
    )
    return runner


def test_reset_observer_and_persistent_turns_preserve_real_state(tmp_path):
    # Given
    runner = configured(tmp_path)
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({"customer": "one"}, trial, 7)
    evidence = runner.trial_evidence(trial)
    # Then
    assert {
        "status": result.status,
        "output": result.output,
        "authoritative": runner.authoritative_artifacts(trial),
        "target_file": read_artifacts(trial, ["state.json"]),
        "phases": [
            (v["phase"], v["moment"], v["status"]) for v in evidence["environment"]["phases"]
        ],
        "turn_messages": [
            v["reply"]["output"]["messages"] for v in evidence["conversation"]["turns"]
        ],
        "initial": evidence["environment"]["initial_state"],
        "final": evidence["environment"]["final_state"],
        "stop": evidence["conversation"]["stop_reason"],
        "leftover_observer_dirs": list(tmp_path.glob("*-environment")),
    } == {
        "status": "completed",
        "output": {"messages": ["Cancel subscription", "Confirm cancellation"]},
        "authoritative": {"state.json": {"subscription": "cancelled", "changes": 1}},
        "target_file": {"state.json": {"subscription": "claimed", "changes": 999}},
        "phases": [
            ("setup", None, "completed"),
            ("reset", None, "completed"),
            ("ready", None, "completed"),
            ("inspect", "initial", "completed"),
            ("inspect", "final", "completed"),
            ("teardown", None, "completed"),
        ],
        "turn_messages": [["Cancel subscription"], ["Cancel subscription", "Confirm cancellation"]],
        "initial": {"state.json": {"subscription": "active", "changes": 0}},
        "final": {"state.json": {"subscription": "cancelled", "changes": 1}},
        "stop": "script_finished",
        "leftover_observer_dirs": [],
    }
    # When: another repetition must begin from the same reset state.
    next_trial = tmp_path / "next-trial"
    next_trial.mkdir()
    next_result = runner.run({"customer": "one"}, next_trial, 7)
    # Then
    assert {
        "status": next_result.status,
        "initial": runner.trial_evidence(next_trial)["environment"]["initial_state"],
        "observer_file_exists": (
            Path(evidence["environment"]["observer_directory"]) / "database.json"
        ).exists(),
    } == {
        "status": "completed",
        "initial": {"state.json": {"subscription": "active", "changes": 0}},
        "observer_file_exists": True,
    }


def test_partial_conversation_and_post_failure_state_survive_target_crash(tmp_path):
    # Given
    runner = configured(
        tmp_path,
        script=SESSION_SCRIPT.replace(
            "history.append(request['message'])",
            "\n    if history: sys.exit(1)\n    history.append(request['message'])",
        ),
    )
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({}, trial, 0)
    evidence = runner.trial_evidence(trial)
    # Then
    assert {
        "status": result.status,
        "turns": [
            {"message": t["user"]["message"], "status": t["status"]}
            for t in evidence["conversation"]["turns"]
        ],
        "observed": runner.authoritative_artifacts(trial),
        "last_phase": evidence["environment"]["phases"][-1]["phase"],
    } == {
        "status": "runner_error",
        "turns": [
            {"message": "Cancel subscription", "status": "completed"},
            {"message": "Confirm cancellation", "status": "runner_error"},
        ],
        "observed": {"state.json": {"subscription": "active", "changes": 0}},
        "last_phase": "teardown",
    }


def test_cancellation_followup_is_an_actual_stateful_turn(tmp_path):
    # Given
    runner = configured(
        tmp_path,
        turns=[
            UserTurn(message="Cancel subscription"),
            UserTurn(message="Actually keep it active"),
        ],
    )
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({}, trial, 0)
    # Then
    assert {"output": result.output, "state": runner.authoritative_artifacts(trial)} == {
        "output": {"messages": ["Cancel subscription", "Actually keep it active"]},
        "state": {"state.json": {"subscription": "active", "changes": 0}},
    }


@pytest.mark.parametrize(
    "replacement,phase",
    [("result={'reset':True}", "reset"), ("result={'ready':state.exists()}", "ready")],
)
def test_unready_or_failed_reset_never_runs_target(tmp_path, replacement, phase):
    # Given
    runner = configured(tmp_path)
    script = tmp_path / "environment.py"
    script.write_text(script.read_text().replace(replacement, "result={}"))
    runner = ConfiguredRunner(runner.config, tmp_path)
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({}, trial, 0)
    # Then
    assert {
        "status": result.status,
        "state": runner.authoritative_artifacts(trial),
        "conversation": runner.trial_evidence(trial)["conversation"],
        "failure_phase": phase in result.error,
    } == {
        "status": "runner_error",
        "state": {},
        "conversation": {},
        "failure_phase": True,
    }


def test_initial_state_drift_is_invalid_and_never_executes_target(tmp_path):
    # Given
    runner = configured(tmp_path)
    runner.config.environment.initial_state_sha256 = digest({"different": True})
    runner = ConfiguredRunner(runner.config, tmp_path)
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({}, trial, 0)
    # Then
    assert {
        "status": result.status,
        "observer": runner.authoritative_artifacts(trial),
        "target_called": (trial / "target-stderr.log").exists(),
    } == {
        "status": "runner_error",
        "observer": {},
        "target_called": False,
    }


def test_source_mutation_mid_session_is_detected_without_explicit_source_files(tmp_path):
    # Given
    runner = configured(
        tmp_path,
        environment=False,
        script="""
import json,sys
from pathlib import Path
request=json.loads(sys.stdin.readline())
Path(__file__).write_text('changed')
print(json.dumps({'message':'okay','output':{'claim':'success'}}), flush=True)
""",
        turns=[UserTurn(message="Run")],
    )
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({}, trial, 0)
    # Then
    assert {
        "status": result.status,
        "output": result.output,
        "source_is_pinned": str(tmp_path / "target.py") in runner.sources,
    } == {
        "status": "runner_error",
        "output": {},
        "source_is_pinned": True,
    }


def test_source_mutation_during_shutdown_invalidates_reply_and_saves_evidence(tmp_path):
    # Given: the target replies before changing its pinned source during shutdown.
    runner = configured(
        tmp_path,
        environment=False,
        script="""
import json,signal,sys
from pathlib import Path

def shutdown(signum=None, frame=None):
    Path(__file__).write_text('changed during shutdown')
    raise SystemExit(0)

signal.signal(signal.SIGTERM, shutdown)
request=json.loads(sys.stdin.readline())
print(json.dumps({'message':'okay','output':{'claim':'success'}}), flush=True)
sys.stdin.read()
shutdown()
""",
        turns=[UserTurn(message="Run")],
    )
    trial = tmp_path / "trial"
    trial.mkdir()
    # When: cleanup detects the changed source after a successfully parsed reply.
    result = runner.run({}, trial, 0)
    record = runner.trial_evidence(trial)["conversation"]
    # Then: the attempt is invalid and its evidence persists instead of raising out of cleanup.
    assert {
        "execution": {"status": result.status, "output": result.output, "error": result.error},
        "interaction": {
            "status": record["status"],
            "stop_reason": record["stop_reason"],
            "error": record["error"],
            "turns": record["turns"],
        },
        "saved_record": json.loads((trial / "interaction.json").read_text()),
    } == {
        "execution": {
            "status": "runner_error",
            "output": {"claim": "success"},
            "error": "Target session cleanup or source validation failed",
        },
        "interaction": {
            "status": "runner_error",
            "stop_reason": "cleanup_error",
            "error": "Target session cleanup or source validation failed",
            "turns": [
                {
                    "index": 0,
                    "user": {"message": "Run"},
                    "reply": {
                        "message": "okay",
                        "output": {"claim": "success"},
                        "evidence": [],
                        "cost_usd": None,
                        "usage": {},
                    },
                    "status": "completed",
                    "error": None,
                }
            ],
        },
        "saved_record": record,
    }


def test_session_timeout_preserves_attempt_and_closes_process(tmp_path):
    # Given
    runner = configured(
        tmp_path,
        environment=False,
        script="import time\ntime.sleep(10)",
        turns=[UserTurn(message="Run")],
        timeout=1,
    )
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({}, trial, 0)
    record = runner.trial_evidence(trial)["conversation"]
    # Then
    assert {
        "status": result.status,
        "statuses": [t["status"] for t in record["turns"]],
        "stop_reason": record["stop_reason"],
    } == {
        "status": "timeout",
        "statuses": ["timeout"],
        "stop_reason": "execution_error",
    }


def test_reactive_simulator_receives_only_actual_interaction_and_can_stop(tmp_path):
    # Given
    runner = configured(tmp_path, environment=False, turns=[UserTurn(message="Begin")])
    simulator = tmp_path / "simulator.py"
    simulator.write_text("""
import json,sys
request=json.load(sys.stdin)
turns=request['interaction']
print(json.dumps({'message':'Clarify please' if len(turns)==1 else None}))
""")
    runner.config.conversation.simulator = SimulatorConfig(command=[sys.executable, str(simulator)])
    runner = ConfiguredRunner(runner.config, tmp_path)
    trial = tmp_path / "trial"
    trial.mkdir()
    # When
    result = runner.run({"private_input_for_target": "not a rubric"}, trial, 0)
    record = runner.trial_evidence(trial)["conversation"]
    # Then
    assert {
        "status": result.status,
        "output": result.output,
        "stop": record["stop_reason"],
        "success": record["success_determined_by"],
    } == {
        "status": "completed",
        "output": {"messages": ["Begin", "Clarify please"]},
        "stop": "simulator_stopped",
        "success": "task_verifier",
    }


def test_target_cannot_fabricate_authoritative_observer_evidence(tmp_path):
    # Given
    script = tmp_path / "spoof.py"
    script.write_text(
        'print(\'{"output": {}, "usage": {"environment": {"artifacts": '
        '{"state.json": {"paid": true}}}}}\')'
    )
    runner = ConfiguredRunner(
        RunnerConfig(
            name="spoof",
            kind="command",
            command=[sys.executable, str(script)],
            environment_version="fixture",
        ),
        tmp_path,
    )
    # When
    result = runner.run({}, tmp_path, 0)
    # Then
    assert {
        "status": result.status,
        "observer": runner.authoritative_artifacts(tmp_path),
        "evidence": runner.trial_evidence(tmp_path),
    } == {
        "status": "completed",
        "observer": {},
        "evidence": {"environment": None, "conversation": None},
    }


def test_per_task_runner_binds_distinct_turns_without_recapturing_changed_sources(tmp_path):
    # Given
    original = configured(tmp_path, environment=False, turns=[UserTurn(message="Original")])
    task_a = original.for_task(None, ConversationSpec(turns=[UserTurn(message="A")]))
    task_b = original.for_task(None, ConversationSpec(turns=[UserTurn(message="B")]))
    trial_a, trial_b = tmp_path / "a", tmp_path / "b"
    trial_a.mkdir()
    trial_b.mkdir()
    # When
    result_a, result_b = task_a.run({}, trial_a, 0), task_b.run({}, trial_b, 0)
    # Then
    assert {
        "a": result_a.output,
        "b": result_b.output,
        "sources": [task_a.sources == original.sources, task_b.sources == original.sources],
        "original_turns": original.config.conversation.model_dump(),
    } == {
        "a": {"messages": ["A"]},
        "b": {"messages": ["B"]},
        "sources": [True, True],
        "original_turns": {
            "turns": [{"message": "Original"}],
            "simulator": None,
            "max_turns": None,
        },
    }
    # When
    (tmp_path / "target.py").write_text("changed implementation")
    # Then
    with pytest.raises(ValueError, match="changed after identity"):
        original.for_task(None, ConversationSpec(turns=[UserTurn(message="C")]))
