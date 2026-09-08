import json
from pathlib import Path

import pytest

from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.data.normalization import load_traces


@pytest.fixture
def sample_data():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def traces(sample_data):
    return load_traces(Path(str(sample_data.joinpath("traces.jsonl"))))


@pytest.fixture
def analysis(sample_data):
    return Analysis.model_validate_json(sample_data.joinpath("analysis.json").read_text())


@pytest.fixture
def outputs(sample_data):
    def read(name):
        return {
            item["case_id"]: item["output"]
            for item in map(json.loads, sample_data.joinpath(name).read_text().splitlines())
        }

    return read
