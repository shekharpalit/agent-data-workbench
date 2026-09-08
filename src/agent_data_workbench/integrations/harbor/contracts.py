"""Explicit configuration for Harbor exports and paired executions."""

from pydantic import Field

from agent_data_workbench.shared.contracts import Contract


class HarborAgentConfig(Contract):
    agent: str = Field(min_length=1)
    model: str = ""
    agent_kwargs: dict[str, str | int | float | bool] = Field(default_factory=dict)


class HarborExportConfig(HarborAgentConfig):
    template_directory: str = Field(min_length=1)
    environment_type: str = Field(default="docker", min_length=1)
    repetitions: int = Field(default=1, ge=1)


class HarborComparisonConfig(Contract):
    template_directory: str = Field(min_length=1)
    baseline: HarborAgentConfig
    candidate: HarborAgentConfig
    environment_type: str = Field(default="docker", min_length=1)
    repetitions: int = Field(default=1, ge=1)
    reward_key: str = Field(default="reward", min_length=1)
    pass_threshold: float = Field(default=1, allow_inf_nan=False)
    timeout: int | None = Field(default=None, ge=1)
