"""Reading what an environment declares, without importing any of it.

`python -m vibepy_core.describe` is run with the environment's own Python and its
output read here. The operating role passes an installed environment's
interpreter; the authoring role passes `uv run --project <dir> python`. Both get
the whole shape the command writes.
"""

import logging
from collections.abc import Sequence
from pathlib import PurePath

from pydantic import TypeAdapter, ValidationError

from vibepy_core.app.entrypoint import DescribedApp
from vibepy_core.errors import ErrorInfo
from vibepy_studio.internals.processes import python_command, reports, run

logger = logging.getLogger(__name__)

_DESCRIBED = TypeAdapter(list[DescribedApp])


class DescribeFailed(Exception):
    """The command did not describe. Carries what it wrote and every report among it."""

    def __init__(self, output: str, *, reports: tuple[ErrorInfo, ...]) -> None:
        """Record `output` for the message and the child's `reports`, in order."""
        super().__init__(output)
        self.output = output
        self.reports = reports


async def describe(
    python: Sequence[str], /, *, cwd: PurePath | None = None
) -> tuple[DescribedApp, ...]:
    """Return what the environment `python` runs in declares.

    Raises:
        NotRunnable: `python[0]` is not a program.
        DescribeFailed: the command exited non-zero, or wrote something that is
            not a list of descriptions.
    """
    completed = await run(python_command(python, "-m", "vibepy_core.describe"), cwd=cwd)
    if completed.returncode != 0:
        raise DescribeFailed(
            (completed.stdout + completed.stderr).strip(), reports=reports(completed.stderr)
        )
    try:
        return tuple(_DESCRIBED.validate_json(completed.stdout))
    except ValidationError as invalid:
        raise DescribeFailed(str(invalid), reports=()) from invalid
