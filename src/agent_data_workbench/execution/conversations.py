"""Continuous conversation trials and their recorded interaction evidence."""

from __future__ import annotations

import copy
import time
from pathlib import Path

from agent_data_workbench.execution.contracts import (
    ConversationSpec,
    Execution,
    ReactiveUser,
    SessionTarget,
)
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import digest


class ConversationRunner:
    def __init__(
        self, target: SessionTarget, spec: ConversationSpec, simulator: ReactiveUser | None = None
    ):
        self.target = target
        self.spec = spec.model_copy(deep=True)
        self.simulator = simulator
        self._evidence: dict[str, dict] = {}

    def identity(self):
        return {
            "target": self.target.identity(),
            "conversation": self.spec.model_dump(),
            "simulator": self.simulator.identity() if self.simulator else None,
        }

    def trial_evidence(self, trial_dir: Path) -> dict:
        return copy.deepcopy(self._evidence.get(str(trial_dir.resolve()), {}))

    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        from agent_data_workbench.execution.contracts import Execution

        started = time.monotonic()
        interaction = []
        result = Execution()
        session = None
        stop_reason = "script_finished"
        next_turn = self.spec.turns[0]
        try:
            session = self.target.open_session(visible_input, trial_dir, seed)
            while next_turn is not None:
                index = len(interaction)
                event = {
                    "index": index,
                    "user": next_turn.model_dump(),
                    "reply": None,
                    "status": "pending",
                    "error": None,
                }
                interaction.append(event)
                # Save the attempted turn before invoking external code.
                save(trial_dir / "interaction.json", {"turns": interaction, "status": "running"})
                reply = session.send(next_turn)
                event.update(reply=reply.model_dump(), status="completed")
                result.output = reply.output
                if reply.cost_usd is not None:
                    result.cost_usd = (result.cost_usd or 0) + reply.cost_usd
                if self.simulator:
                    if self.spec.max_turns is not None and len(interaction) >= self.spec.max_turns:
                        stop_reason = "turn_limit"
                        break
                    next_turn = self.simulator.next_turn(copy.deepcopy(interaction))
                    if next_turn is None:
                        stop_reason = "simulator_stopped"
                else:
                    next_turn = (
                        self.spec.turns[index + 1] if index + 1 < len(self.spec.turns) else None
                    )
        except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
            result.status = "timeout" if isinstance(exc, TimeoutError) else "runner_error"
            result.error = "Conversation failed; inspect the recorded partial interaction"
            stop_reason = "execution_error"
            if interaction and interaction[-1]["status"] == "pending":
                interaction[-1].update(status=result.status, error=result.error)
        finally:
            if session is not None:
                try:
                    session.close()
                except OSError, RuntimeError, ValueError:
                    result.status = "runner_error"
                    result.error = "Target session cleanup or source validation failed"
                    stop_reason = "cleanup_error"
            result.latency_seconds = time.monotonic() - started
            record = {
                "spec_sha256": digest(self.spec.model_dump()),
                "turns": interaction,
                "status": result.status,
                "stop_reason": stop_reason,
                "success_determined_by": "task_verifier",
                "evidence_source": "target_session_adapter",
                "session_id": getattr(session, "session_id", None),
                "error": result.error,
                "simulator": self.simulator.identity() if self.simulator else None,
            }
            self._evidence[str(trial_dir.resolve())] = copy.deepcopy(record)
            save(trial_dir / "interaction.json", record)
        return result
