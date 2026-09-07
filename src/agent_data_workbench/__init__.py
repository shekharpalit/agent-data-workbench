"""Evidence-linked agent analysis, with pluggable analyzer backends."""

from .backends import Analyzer, CliAnalyzer
from .calibration import (
    AttemptLabel,
    adjudicate_attempt,
    calibration_summary,
    create_calibration,
    label_attempt,
)
from .conversations import ConversationSpec, UserTurn
from .coverage import CoverageMapping, TaxonomySpec, coverage_report, create_taxonomy, map_coverage
from .environments import EnvironmentConfig
from .experiments import make_suite, run_experiment
from .harbor import HarborExportConfig, export_harbor, run_harbor_export
from .improvements import create_improvement, decide_improvement
from .ingestion import FilesSource, SourceFile, discover_files
from .models import Analysis, Trace
from .project import Project
from .research import NativeSession, ResearchWorkspace, investigate, start_investigation
from .runners import ConfiguredRunner, TargetRunner
from .store import JsonSource, TraceSource, TraceStore
from .tasks import TaskSpec, audit_task, design_tasks, grade
from .traces import load_traces, normalize
from .workflow import analyze_traces, complete_run, prepare_run
from .worlds import WorldReference, WorldSpec, create_world, review_world

__version__ = "0.5.0"
__all__ = [
    "FilesSource",
    "SourceFile",
    "discover_files",
    "AttemptLabel",
    "adjudicate_attempt",
    "calibration_summary",
    "create_calibration",
    "label_attempt",
    "ConversationSpec",
    "UserTurn",
    "CoverageMapping",
    "TaxonomySpec",
    "coverage_report",
    "create_taxonomy",
    "map_coverage",
    "EnvironmentConfig",
    "HarborExportConfig",
    "export_harbor",
    "run_harbor_export",
    "create_improvement",
    "decide_improvement",
    "WorldReference",
    "WorldSpec",
    "create_world",
    "review_world",
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
