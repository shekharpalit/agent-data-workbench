"""Evidence-linked agent analysis, with pluggable analyzer backends."""

from .backends import Analyzer, CliAnalyzer
from .experiments import make_suite, run_experiment
from .models import Analysis, Trace
from .project import Project
from .research import NativeSession, ResearchWorkspace, investigate, start_investigation
from .runners import ConfiguredRunner, TargetRunner
from .store import JsonSource, TraceSource, TraceStore
from .tasks import TaskSpec, audit_task, design_tasks, grade
from .traces import load_traces, normalize
from .workflow import analyze_traces, complete_run, prepare_run

__version__ = "0.4.0"
__all__ = [
    "Analysis",
    "Analyzer",
    "CliAnalyzer",
    "Trace",
    "analyze_traces",
    "complete_run",
    "load_traces",
    "normalize",
    "prepare_run",
    "Project",
    "TraceStore",
    "TraceSource",
    "JsonSource",
    "TaskSpec",
    "TargetRunner",
    "ConfiguredRunner",
    "NativeSession",
    "ResearchWorkspace",
    "investigate",
    "start_investigation",
    "design_tasks",
    "audit_task",
    "grade",
    "make_suite",
    "run_experiment",
]
