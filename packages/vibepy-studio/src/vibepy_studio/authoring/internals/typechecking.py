"""Running the type checker over a source project, in that project's environment.

The framework's contracts for a handler, a configuration and a lifespan are
types, and PEP 484 places their checking in an offline type checker. pyright is
that authority here, as it is for this repository. `uv run --with` lays it over
the project's own environment for one invocation, so the project's
`pyproject.toml`, lock and environment are untouched and the project's own
`[tool.pyright]`, or pyright's default `standard` mode, applies.

pyright's `--outputjson` is read as the shape it documents; nothing is dropped.

pyright resolves its configuration by walking upward from `-p`'s directory,
so a project with no `[tool.pyright]` of its own inherits whatever an
ancestor directory declares -- in this repository, the workspace root's
`include`, which names every member. `command` therefore also names
`project` as a positional file argument: pyright analyses only the paths
given on the command line, whatever configuration -- the project's own or
an inherited one -- decided how to check them.
"""

import logging
from collections.abc import Sequence
from pathlib import PurePath

from pydantic import BaseModel, ValidationError

from vibepy_studio.authoring.models import Severity
from vibepy_studio.internals import run

logger = logging.getLogger(__name__)

PYRIGHT = "pyright[nodejs]"
"""The distribution `uv run --with` injects: pyright with Node bundled as wheels."""


class PyrightPosition(BaseModel):
    """A zero-based line, as pyright writes it."""

    line: int


class PyrightRange(BaseModel):
    """Where a diagnostic starts; the end is not read."""

    start: PyrightPosition


class PyrightDiagnostic(BaseModel):
    """One entry of `generalDiagnostics`, the fields read."""

    file: str
    severity: Severity
    message: str
    range: PyrightRange
    rule: str | None = None


class PyrightOutput(BaseModel):
    """What `--outputjson` writes, the part read."""

    generalDiagnostics: list[PyrightDiagnostic]


class TypecheckFailed(Exception):
    """pyright did not answer: it exited with a code that is not a verdict."""

    def __init__(self, output: str) -> None:
        """Record what pyright wrote."""
        super().__init__(output)
        self.output = output


def command(project: PurePath, /) -> list[str]:
    """Return the command that type-checks `project` inside its environment. Pure."""
    return [
        "uv",
        "run",
        "--project",
        str(project),
        "--with",
        PYRIGHT,
        "pyright",
        "--outputjson",
        "-p",
        str(project),
        str(project),
    ]


async def typecheck(project: PurePath, /) -> Sequence[PyrightDiagnostic]:
    """Return every diagnostic pyright reports for `project`, at pyright's own severity.

    Raises:
        NotRunnable: uv is not runnable.
        TypecheckFailed: pyright exited 2, 3 or 4, or wrote something that is not its JSON.
    """
    completed = await run(command(project))
    if completed.returncode not in (0, 1):
        raise TypecheckFailed((completed.stdout + completed.stderr).strip())
    try:
        return PyrightOutput.model_validate_json(completed.stdout).generalDiagnostics
    except ValidationError as invalid:
        logger.debug("pyright wrote something other than its JSON", exc_info=invalid)
        raise TypecheckFailed(completed.stdout.strip()) from invalid
