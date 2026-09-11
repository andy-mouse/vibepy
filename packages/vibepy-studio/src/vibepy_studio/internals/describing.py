"""Reading what an environment declares, without importing any of it.

`python -m vibepy_core.describe` is run with the environment's own Python and its
output read here. The consumption role passes an installed environment's
interpreter; the authoring role passes `uv run --project <dir> python`. Both get
the whole shape the command writes.
"""

import logging
from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError

from vibepy_core.errors import ErrorInfo
from vibepy_studio.internals.processes import reported, run
from vibepy_studio.models import Described

logger = logging.getLogger(__name__)

_DESCRIBED = TypeAdapter(list[Described])


class DescribeFailed(Exception):
    """The command did not describe. Carries what it wrote and any report among it."""

    def __init__(self, output: str, *, reported: ErrorInfo | None) -> None:
        """Record `output` for the message and the child's `reported` failure, if any."""
        super().__init__(output)
        self.output = output
        self.reported = reported


async def describe(python: Sequence[str], /) -> tuple[Described, ...]:
    """Return what the environment `python` runs in declares.

    Raises:
        NotRunnable: `python[0]` is not a program.
        DescribeFailed: the command exited non-zero, or wrote something that is
            not a list of descriptions.
    """
    completed = await run([*python, "-m", "vibepy_core.describe"])
    if completed.returncode != 0:
        raise DescribeFailed(
            (completed.stdout + completed.stderr).strip(), reported=reported(completed.stderr)
        )
    try:
        return tuple(_DESCRIBED.validate_json(completed.stdout))
    except ValidationError as invalid:
        raise DescribeFailed(str(invalid), reported=None) from invalid
