"""Native-agent research over a durable, complete data workspace."""

from .artifacts import investigation_view, load_investigation, research_store, start_investigation
from .contracts import Edit, Proposal, ResearchResult, Signal
from .proposals import export_proposal
from .reporting import research_report
from .sessions import NativeSession, investigate, pause_investigation
from .validation import validate_result
from .workspace import ResearchWorkspace

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
