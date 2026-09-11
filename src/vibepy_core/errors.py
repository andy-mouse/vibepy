"""Framework exceptions and the channel-neutral form a channel reports them in.

Exception types are the contract inside Python. A code is the projection of a type
across a boundary a Python type cannot cross, which is why every exception carries
one and why a code, once published, keeps its meaning for good.

Categories are mapped here rather than declared on each exception: a category is a
property of the code, and one table is easier to keep exhaustive than eight
scattered declarations.
"""

import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

UNHANDLED_CODE = "app.unhandled"
"""The code for a failure the framework did not define. It belongs to no exception."""


class ErrorCategory(StrEnum):
    """What kind of failure this is, independently of which one it is.

    A caller reads it to learn whether a different call could succeed. A future
    REST adapter reads it to choose between 4xx and 5xx.
    """

    CALLER = "caller"
    EXECUTION = "execution"
    DECLARATION = "declaration"


class VibepyError(Exception):
    """Base class for every exception raised by the framework."""

    code: ClassVar[str]

    def details(self) -> Mapping[str, str]:
        """Return the values this error's message interpolates.

        An agent reads these rather than parsing the sentence, so a message may be
        reworded without breaking anyone.
        """
        return {}


class ToolNotFoundError(VibepyError):
    """No Tool is registered under the requested name."""

    code = "tool.not_found"

    def __init__(self, tool_name: str) -> None:
        """Record `tool_name` for the message and for `details()`."""
        super().__init__(f"No Tool is registered under the name {tool_name!r}")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        """Return `tool_name`."""
        return {"tool_name": self.tool_name}


class ToolInputValidationError(VibepyError):
    """Raw input did not satisfy the Tool's input model."""

    code = "tool.input_invalid"

    def __init__(self, tool_name: str) -> None:
        """Record `tool_name` for the message and for `details()`."""
        super().__init__(f"Input for Tool {tool_name!r} failed validation")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        """Return `tool_name`."""
        return {"tool_name": self.tool_name}


class ToolOutputValidationError(VibepyError):
    """A handler result did not satisfy the Tool's output model."""

    code = "tool.output_invalid"

    def __init__(self, tool_name: str) -> None:
        """Record `tool_name` for the message and for `details()`."""
        super().__init__(f"Output of Tool {tool_name!r} failed validation")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        """Return `tool_name`."""
        return {"tool_name": self.tool_name}


class ToolNameConflictError(VibepyError):
    """Two Tools declared the same name."""

    code = "tool.name_conflict"

    def __init__(self, tool_name: str) -> None:
        """Record `tool_name` for the message and for `details()`."""
        super().__init__(f"Two Tools declare the name {tool_name!r}")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        """Return `tool_name`."""
        return {"tool_name": self.tool_name}


class PageNotFoundError(VibepyError):
    """No Page is registered under the requested name."""

    code = "page.not_found"

    def __init__(self, page_name: str) -> None:
        """Record `page_name` for the message and for `details()`."""
        super().__init__(f"No Page is registered under the name {page_name!r}")
        self.page_name = page_name

    def details(self) -> Mapping[str, str]:
        """Return `page_name`."""
        return {"page_name": self.page_name}


class PageRouteInvalidError(VibepyError):
    """A Page declared a route the Web channel cannot register."""

    code = "page.route_invalid"

    def __init__(self, page_name: str, route: str) -> None:
        """Record `page_name` and `route` for the message and for `details()`."""
        super().__init__(f"Page {page_name!r} declared the invalid route {route!r}")
        self.page_name = page_name
        self.route = route

    def details(self) -> Mapping[str, str]:
        """Return `page_name` and `route`."""
        return {"page_name": self.page_name, "route": self.route}


class PageRouteConflictError(VibepyError):
    """Two Pages declared the same route."""

    code = "page.route_conflict"

    def __init__(self, route: str, page_name: str, conflicting_page_name: str) -> None:
        """Record `route`, `page_name` and `conflicting_page_name` for `details()`."""
        super().__init__(
            f"Pages {page_name!r} and {conflicting_page_name!r} both declare the route {route!r}"
        )
        self.route = route
        self.page_name = page_name
        self.conflicting_page_name = conflicting_page_name

    def details(self) -> Mapping[str, str]:
        """Return `route`, `page_name` and `conflicting_page_name`."""
        return {
            "route": self.route,
            "page_name": self.page_name,
            "conflicting_page_name": self.conflicting_page_name,
        }


class PageNameConflictError(VibepyError):
    """Two Pages declared the same name."""

    code = "page.name_conflict"

    def __init__(self, page_name: str, route: str, conflicting_route: str) -> None:
        """Record `page_name`, `route` and `conflicting_route` for `details()`."""
        super().__init__(
            f"Pages at {route!r} and {conflicting_route!r} both declare the name {page_name!r}"
        )
        self.page_name = page_name
        self.route = route
        self.conflicting_route = conflicting_route

    def details(self) -> Mapping[str, str]:
        """Return `page_name`, `route` and `conflicting_route`."""
        return {
            "page_name": self.page_name,
            "route": self.route,
            "conflicting_route": self.conflicting_route,
        }


class AppConfigInvalidError(VibepyError):
    """Raw configuration did not satisfy the App's declared configuration model."""

    code = "config.invalid"

    def __init__(self, app_id: str, fields: Sequence[str]) -> None:
        """Record `app_id` and the invalid `fields` for the message and for `details()`."""
        named = ", ".join(fields)
        super().__init__(f"Configuration for App {app_id!r} failed validation at {named}")
        self.app_id = app_id
        self.fields = tuple(fields)

    def details(self) -> Mapping[str, str]:
        """Return `app_id` and the invalid fields, joined."""
        return {"app_id": self.app_id, "fields": ", ".join(self.fields)}


class AppEntrypointUnloadableError(VibepyError):
    """A declared entrypoint could not be resolved: no such module, or no such attribute."""

    code = "package.entrypoint_unloadable"

    def __init__(self, app_name: str, reference: str) -> None:
        """Record `app_name` and `reference` for the message and for `details()`."""
        super().__init__(f"Entrypoint {reference!r} declared by App {app_name!r} did not load")
        self.app_name = app_name
        self.reference = reference

    def details(self) -> Mapping[str, str]:
        """Return `app_name` and `reference`."""
        return {"app_name": self.app_name, "reference": self.reference}


class AppEntrypointInvalidError(VibepyError):
    """A declared entrypoint resolved to something other than an AppEntrypoint."""

    code = "package.entrypoint_invalid"

    def __init__(self, app_name: str, reference: str, found: str) -> None:
        """Record `app_name`, `reference` and what was `found` for `details()`."""
        super().__init__(
            f"Entrypoint {reference!r} declared by App {app_name!r} resolved to {found}"
        )
        self.app_name = app_name
        self.reference = reference
        self.found = found

    def details(self) -> Mapping[str, str]:
        """Return `app_name`, `reference` and `found`."""
        return {"app_name": self.app_name, "reference": self.reference, "found": self.found}


class AppNotDeclaredError(VibepyError):
    """No App of that name is declared in this environment."""

    code = "package.app_not_declared"

    def __init__(self, app_name: str) -> None:
        """Record `app_name` for the message and for `details()`."""
        super().__init__(f"No App named {app_name!r} is declared in this environment")
        self.app_name = app_name

    def details(self) -> Mapping[str, str]:
        """Return `app_name`."""
        return {"app_name": self.app_name}


class InvokeRequestInvalidError(VibepyError):
    """Standard input did not carry one JSON object of `input`."""

    code = "invoke.request_invalid"

    def __init__(self) -> None:
        """State that standard input was not one JSON object of `input`."""
        super().__init__("The request on standard input is not a JSON object of input")


ERROR_CATALOG: Mapping[str, ErrorCategory] = {
    ToolNotFoundError.code: ErrorCategory.CALLER,
    ToolInputValidationError.code: ErrorCategory.CALLER,
    ToolOutputValidationError.code: ErrorCategory.EXECUTION,
    ToolNameConflictError.code: ErrorCategory.DECLARATION,
    PageNotFoundError.code: ErrorCategory.CALLER,
    PageRouteInvalidError.code: ErrorCategory.DECLARATION,
    PageRouteConflictError.code: ErrorCategory.DECLARATION,
    PageNameConflictError.code: ErrorCategory.DECLARATION,
    AppConfigInvalidError.code: ErrorCategory.CALLER,
    AppEntrypointUnloadableError.code: ErrorCategory.DECLARATION,
    AppEntrypointInvalidError.code: ErrorCategory.DECLARATION,
    AppNotDeclaredError.code: ErrorCategory.CALLER,
    InvokeRequestInvalidError.code: ErrorCategory.CALLER,
    UNHANDLED_CODE: ErrorCategory.EXECUTION,
}
"""Every framework code and its category, `app.unhandled` included.

Public so that a reader outside the framework — an authoring Tool describing
the framework to an agent — states the same catalogue this module classifies by.
"""


@dataclass(frozen=True)
class ErrorInfo:
    """One failure, in the form every channel reports.

    Carries no channel type and no channel vocabulary, so the Web channel, the
    Agent channel and any future one describe the same failure the same way.
    """

    code: str
    category: ErrorCategory
    message: str
    details: Mapping[str, str]


def to_error_info(error: Exception, /) -> ErrorInfo:
    """Describe any exception in the channel-neutral form.

    Normalizing is not wrapping. The exception itself still propagates untouched;
    this is called only where a channel must render an answer.

    A code this table does not map is described rather than classified, whatever
    raised it. `VibepyError` is exported, so an App may subclass it, and its
    `code` is an unassigned ClassVar on the base itself. The catalogue test is
    what guarantees no framework exception takes that path.
    """
    if isinstance(error, VibepyError):
        code: object = getattr(error, "code", None)
        if isinstance(code, str):
            category = ERROR_CATALOG.get(code)
            if category is not None:
                return ErrorInfo(
                    code=code,
                    category=category,
                    message=str(error),
                    details=error.details(),
                )
    return ErrorInfo(
        code=UNHANDLED_CODE,
        category=ErrorCategory.EXECUTION,
        message=str(error),
        details={},
    )


def report_line(info: ErrorInfo, /) -> str:
    """One failure as the line a command writes to standard error.

    `describe`, `serve` and `invoke` write it, and a host reads all three with
    one reader, which is why the shape lives here and not in each command.
    """
    return (
        json.dumps(
            {
                "code": info.code,
                "category": info.category,
                "message": info.message,
                "details": dict(info.details),
            }
        )
        + "\n"
    )


def report(error: Exception, /) -> None:
    """Write one failure where whatever started this process can read it."""
    sys.stderr.write(report_line(to_error_info(error)))


class _Report(BaseModel):
    """One report line, as read rather than as written.

    `code` is required, because that is what distinguishes a report from any
    other line a command's standard error carries. The rest carry defaults, so a
    line written by an older version of the format still reads.

    `category` is read as a string and typed afterwards: a value this framework
    does not know is a fact about the writer, not a parse failure.
    """

    code: str
    category: str = "execution"
    message: str = ""
    details: dict[str, str] = {}


_REPORT = TypeAdapter(_Report)


def read_report_line(line: str, /) -> ErrorInfo | None:
    """Read one line as the failure `report_line` writes, or `None` if it is not one.

    Reading belongs beside writing. There are three writers -- `describe`,
    `serve` and `invoke` -- and one format; a reader kept outside the framework
    would be a second statement of that format, free to drift from it.

    A category this framework does not know is read as `EXECUTION`: a host
    still learns that something failed, and learns it from the same shape.
    """
    try:
        parsed = _REPORT.validate_json(line)
    except ValidationError:
        return None
    try:
        category = ErrorCategory(parsed.category)
    except ValueError:
        logger.debug("a report named an unknown category: %s", parsed.category)
        category = ErrorCategory.EXECUTION
    return ErrorInfo(
        code=parsed.code,
        category=category,
        message=parsed.message,
        details=parsed.details,
    )
