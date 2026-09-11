"""What both of Studio's roles say the same way: a diagnostic, and an empty input.

Also holds the shape `python -m vibepy_core.describe` writes, which both roles
read and authoring publishes.
"""

import logging

from pydantic import BaseModel

from vibepy_core import ErrorCategory

logger = logging.getLogger(__name__)


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""


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


# Imported here, below the models above, rather than at module top: `describing`
# (inside `vibepy_studio.internals`) imports `Described` from this module, and
# `vibepy_studio.internals` is a package whose `__init__` runs before any of its
# submodules — including `processes` — become importable. Importing `ChildFailure`
# before `Described` exists would make that a circular import.
from vibepy_studio.internals.processes import ChildFailure  # noqa: E402


def category(reported: str, /) -> ErrorCategory:
    """Return the category a child named, or execution when it named one we do not know."""
    try:
        return ErrorCategory(reported)
    except ValueError:
        logger.debug("a child reported an unknown category: %s", reported)
        return ErrorCategory.EXECUTION


def diagnostic_of(reported: ChildFailure, /, **details: str) -> Diagnostic:
    """Carry a failure a child reported, with its own code and category, plus `details`."""
    return Diagnostic(
        code=reported.code,
        category=category(reported.category),
        message=reported.message,
        details={**details, **reported.details},
    )
