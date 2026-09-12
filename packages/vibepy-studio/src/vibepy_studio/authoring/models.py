"""What the authoring Tools take and return, and the `authoring.*` vocabulary.

| Code | Category | Reports |
| --- | --- | --- |
| `authoring.project_not_found` | caller | `project` holds no `pyproject.toml`, or one with no |
|  |  | `[project].name` |
| `authoring.uv_unavailable` | execution | `uv` is not runnable from Studio's process |
| `authoring.environment_failed` | execution | uv exited non-zero with no framework report; what |
|  |  | it wrote is the message |
| `authoring.no_apps_declared` | declaration | the project's environment declares nothing under |
|  |  | the project's distribution |
| `authoring.type_error` | declaration | pyright reported this, at its own severity; `file`, |
|  |  | `line` (1-based) and `rule` say where and which |

A framework failure the child reports travels with its own code and category and
is not restated here.
"""

from collections.abc import Sequence
from enum import StrEnum
from pathlib import PurePath

from pydantic import BaseModel, JsonValue

from vibepy_core.app import DescribedApp
from vibepy_core.app.group import APP_GROUP
from vibepy_core.errors import ErrorCategory, ErrorInfo
from vibepy_studio.models import diagnostic_of


class ErrorCode(BaseModel):
    """One framework code and its category."""

    code: str
    category: ErrorCategory


class FrameworkDescription(BaseModel):
    """What `vibepy_core` asserts about itself."""

    framework_version: str
    entry_point_group: str
    channel_extras: list[str]
    error_catalog: list[ErrorCode]


class InspectRequest(BaseModel):
    """A project to inspect: the directory holding its `pyproject.toml`."""

    project: PurePath


class AppInspection(BaseModel):
    """What a project declares, or every reason it could not be read."""

    apps: list[DescribedApp]
    diagnostics: list[ErrorInfo] = []


class Severity(StrEnum):
    """A pyright diagnostic's own severity."""

    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"


class Diagnostic(BaseModel):
    """One conformance finding, at its own severity."""

    severity: Severity
    error: ErrorInfo


class ValidateRequest(BaseModel):
    """A project to validate: the directory holding its `pyproject.toml`."""

    project: PurePath


class AppValidation(BaseModel):
    """Whether a project conforms, and every diagnostic that says why not."""

    conforms: bool
    diagnostics: list[Diagnostic]


class InvokeRequest(BaseModel):
    """One Tool of one App a project declares, with the App's configuration and the Tool's input."""

    project: PurePath
    app: str
    tool: str
    input: dict[str, JsonValue] = {}
    config: dict[str, JsonValue] = {}


class Invocation(BaseModel):
    """What the Tool returned, or why it did not."""

    output: dict[str, object] | None = None
    diagnostic: ErrorInfo | None = None


def uv_unavailable(project: PurePath, /) -> ErrorInfo:
    """Say uv is not runnable from this process."""
    return ErrorInfo(
        code="authoring.uv_unavailable",
        category=ErrorCategory.EXECUTION,
        message="uv is not available to Studio; install uv and put it on PATH",
        details={"project": str(project)},
    )


def environment_failed(project: PurePath, output: str, /) -> ErrorInfo:
    """Say uv exited non-zero and the child made no framework report of its own."""
    return ErrorInfo(
        code="authoring.environment_failed",
        category=ErrorCategory.EXECUTION,
        message=output,
        details={"project": str(project)},
    )


def project_not_found(project: PurePath, reason: str, /) -> ErrorInfo:
    """Say why `project` is not a project a Tool can read."""
    return ErrorInfo(
        code="authoring.project_not_found",
        category=ErrorCategory.CALLER,
        message=f"{project} {reason}",
        details={"project": str(project)},
    )


def no_apps_declared(project: PurePath, distribution: str, /) -> ErrorInfo:
    """Say the project's own distribution declares no App."""
    return ErrorInfo(
        code="authoring.no_apps_declared",
        category=ErrorCategory.DECLARATION,
        message=f"{distribution!r} declares no App in the {APP_GROUP!r} entry point group",
        details={"project": str(project), "distribution": distribution},
    )


def from_reports(
    project: PurePath, reported: Sequence[ErrorInfo], output: str, /, **details: str
) -> list[ErrorInfo]:
    """Carry the child's own reports when it made any, else the environment as the failure."""
    if not reported:
        return [environment_failed(project, output)]
    return [diagnostic_of(info, project=str(project), **details) for info in reported]


def type_error(
    project: PurePath, *, file: str, line: int, rule: str | None, message: str
) -> ErrorInfo:
    """Carry one pyright diagnostic as the framework's shape; pyright's sentence is the message."""
    details = {"project": str(project), "file": file, "line": str(line)}
    if rule is not None:
        details["rule"] = rule
    return ErrorInfo(
        code="authoring.type_error",
        category=ErrorCategory.DECLARATION,
        message=message,
        details=details,
    )


def validation(diagnostics: Sequence[Diagnostic], /) -> AppValidation:
    """Say whether the project conforms: no diagnostic of severity `error`."""
    return AppValidation(
        conforms=not any(d.severity is Severity.ERROR for d in diagnostics),
        diagnostics=list(diagnostics),
    )
