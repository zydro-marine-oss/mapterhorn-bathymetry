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
