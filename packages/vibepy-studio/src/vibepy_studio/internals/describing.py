"""Reading what an environment declares, without importing any of it.

`python -m vibepy_core.describe` is run with the environment's own Python and its
output read here. The consumption role passes an installed environment's
interpreter; the authoring role passes `uv run --project <dir> python`. Both get
the whole shape the command writes.
"""

import logging
from collections.abc import Sequence

from pydantic import BaseModel, TypeAdapter, ValidationError

from vibepy_studio.internals.processes import ChildFailure, reported, run

logger = logging.getLogger(__name__)


class DescribedTool(BaseModel):
    """One Tool, as `describe` writes it."""

    name: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]


class DescribedPage(BaseModel):
    """One Page, as `describe` writes it."""

    name: str
    route: str
    title: str


class Described(BaseModel):
    """One entry of what `describe` writes: the declaration's identity and its description."""

    app_name: str
    distribution: str
    distribution_version: str
    app_id: str
    name: str
    version: str
    config_schema: dict[str, object] = {}
    tools: list[DescribedTool] = []
    pages: list[DescribedPage] = []


_DESCRIBED = TypeAdapter(list[Described])


class DescribeFailed(Exception):
    """The command did not describe. Carries what it wrote and any report among it."""

    def __init__(self, output: str, *, reported: ChildFailure | None) -> None:
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
