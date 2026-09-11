"""What both of Studio's roles say the same way: a diagnostic, and an empty input.

A failure a channel renders is `vibepy_core`'s own `ErrorInfo`: it already
crosses a process boundary between an App's environment and Studio, and a
second declaration of the same four fields would be free to drift from it.
"""

from pydantic import BaseModel

from vibepy_core.errors import ErrorInfo


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""


def diagnostic_of(reported: ErrorInfo, /, **details: str) -> ErrorInfo:
    """Carry a failure a child reported, with its own code and category, plus `details`."""
    return reported.model_copy(update={"details": {**details, **reported.details}})
