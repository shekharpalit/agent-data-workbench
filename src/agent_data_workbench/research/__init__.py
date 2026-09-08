"""Native-agent research over a durable, complete data workspace."""

from agent_data_workbench.research.artifacts import (
    investigation_view,
    load_investigation,
    research_store,
    start_investigation,
)
from agent_data_workbench.research.contracts import Edit, Proposal, ResearchResult, Signal
from agent_data_workbench.research.proposals import export_proposal
from agent_data_workbench.research.reporting import research_report
from agent_data_workbench.research.sessions import NativeSession, investigate, pause_investigation
from agent_data_workbench.research.validation import validate_result
from agent_data_workbench.research.workspace import ResearchWorkspace

__all__ = [
    "Edit",
    "Proposal",
    "ResearchResult",
    "Signal",
    "NativeSession",
    "ResearchWorkspace",
    "start_investigation",
    "load_investigation",
    "investigation_view",
    "research_store",
    "investigate",
    "pause_investigation",
    "export_proposal",
    "research_report",
    "validate_result",
]
