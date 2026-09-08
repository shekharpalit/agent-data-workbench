"""Evidence-linked agent analysis, with pluggable analyzer backends."""

from agent_data_workbench.analysis.batch import analyze_traces, complete_run, prepare_run
from agent_data_workbench.analysis.contracts import Analysis
from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.discovery import SourceFile, discover_files
from agent_data_workbench.data.imports import import_dataset
from agent_data_workbench.data.ingestion import FilesSource
from agent_data_workbench.data.normalization import load_traces, normalize
from agent_data_workbench.data.sources import JsonSource, TraceSource
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.evaluation.calibration import (
    AttemptLabel,
    adjudicate_attempt,
    calibration_summary,
    create_calibration,
    label_attempt,
)
from agent_data_workbench.evaluation.coverage import (
    CoverageMapping,
    TaxonomySpec,
    coverage_report,
    create_taxonomy,
    map_coverage,
)
from agent_data_workbench.evaluation.experiments import run_experiment
from agent_data_workbench.evaluation.improvements import create_improvement, decide_improvement
from agent_data_workbench.evaluation.suites import make_suite
from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.evaluation.tasks.design import design_tasks
from agent_data_workbench.evaluation.tasks.grading import audit_task, grade
from agent_data_workbench.evaluation.worlds import (
    WorldReference,
    WorldSpec,
    create_world,
    review_world,
)
from agent_data_workbench.execution.contracts import (
    ConversationSpec,
    EnvironmentConfig,
    TargetRunner,
    UserTurn,
)
from agent_data_workbench.execution.runners import ConfiguredRunner
from agent_data_workbench.integrations.analyzers import Analyzer, CliAnalyzer
from agent_data_workbench.integrations.harbor import (
    HarborAgentConfig,
    HarborComparisonConfig,
    HarborExportConfig,
    compare_harbor,
    export_harbor,
    run_harbor_export,
)
from agent_data_workbench.integrations.huggingface import DatasetImport, HuggingFaceSource
from agent_data_workbench.research import (
    NativeSession,
    ResearchWorkspace,
    investigate,
    start_investigation,
)
from agent_data_workbench.workspace.project import Project

__version__ = "0.1.0"
__all__ = [
    "DatasetImport",
    "HuggingFaceSource",
    "import_dataset",
    "HarborAgentConfig",
    "HarborComparisonConfig",
    "compare_harbor",
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
