"""What both of Studio's roles say the same way: a diagnostic, and an empty input."""

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


def category(reported: str, /) -> ErrorCategory:
    """Return the category a child named, or execution when it named one we do not know."""
    try:
        return ErrorCategory(reported)
    except ValueError:
        logger.debug("a child reported an unknown category: %s", reported)
        return ErrorCategory.EXECUTION
