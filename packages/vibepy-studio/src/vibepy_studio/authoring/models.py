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

A framework failure the child reports travels with its own code and category and
is not restated here.
"""

from pathlib import Path

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

    project: Path


class AppInspection(BaseModel):
    """What a project declares, or why that could not be read."""

    apps: list[DescribedApp]
    diagnostic: ErrorInfo | None = None


class InvokeRequest(BaseModel):
    """One Tool of one App a project declares, with the App's configuration and the Tool's input."""

    project: Path
    app: str
    tool: str
    input: dict[str, JsonValue] = {}
    config: dict[str, JsonValue] = {}


class Invocation(BaseModel):
    """What the Tool returned, or why it did not."""

    output: dict[str, object] | None = None
    diagnostic: ErrorInfo | None = None


def uv_unavailable(project: Path, /) -> ErrorInfo:
    """Say uv is not runnable from this process."""
    return ErrorInfo(
        code="authoring.uv_unavailable",
        category=ErrorCategory.EXECUTION,
        message="uv is not available to Studio; install uv and put it on PATH",
        details={"project": str(project)},
    )


def environment_failed(project: Path, output: str, /) -> ErrorInfo:
    """Say uv exited non-zero and the child made no framework report of its own."""
    return ErrorInfo(
        code="authoring.environment_failed",
        category=ErrorCategory.EXECUTION,
        message=output,
        details={"project": str(project)},
    )


def project_not_found(project: Path, reason: str, /) -> ErrorInfo:
    """Say why `project` is not a project a Tool can read."""
    return ErrorInfo(
        code="authoring.project_not_found",
        category=ErrorCategory.CALLER,
        message=f"{project} {reason}",
        details={"project": str(project)},
    )


def no_apps_declared(project: Path, distribution: str, /) -> ErrorInfo:
    """Say the project's own distribution declares no App."""
    return ErrorInfo(
        code="authoring.no_apps_declared",
        category=ErrorCategory.DECLARATION,
        message=f"{distribution!r} declares no App in the {APP_GROUP!r} entry point group",
        details={"project": str(project), "distribution": distribution},
    )


def from_report(
    project: Path, reported: ErrorInfo | None, output: str, /, **details: str
) -> ErrorInfo:
    """Carry the child's own report when it made one, else the environment as the failure.

    A child that reached the framework reports in the framework's vocabulary,
    and that report travels as it is. `authoring.environment_failed` is what is
    left to say when it did not.
    """
    if reported is None:
        return environment_failed(project, output)
    return diagnostic_of(reported, project=str(project), **details)
