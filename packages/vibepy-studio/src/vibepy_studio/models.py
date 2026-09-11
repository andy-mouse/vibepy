"""What both of Studio's roles say the same way: a diagnostic, and an empty input."""

from pydantic import BaseModel

from vibepy_core import ErrorCategory


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""
