# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "rich>=13.0.0",
# ]
#
# [tool.pixi.workspace]
# channels = ["conda-forge"]
# ///

# Shared Rich progress bars for covering / run pipelines.
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


def make_progress():
    return Progress(
        SpinnerColumn(),
        TextColumn('{task.description}', justify='left'),
        BarColumn(bar_width=28),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        expand=True,
    )
