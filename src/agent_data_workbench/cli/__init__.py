"""Compose command groups; each domain owns its command implementations."""

import typer

from . import batch, benchmark, experiments, exports, knowledge, project, research, tasks

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Research agent traces and execute reviewed improvement experiments.",
)
for group in (project, research, experiments, exports, benchmark, batch):
    app.add_typer(group.app)
app.add_typer(knowledge.app, name="knowledge", help="Review versioned project knowledge.")
app.add_typer(tasks.app, name="task", help="Design, audit and review tasks.")
