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

from pydantic import BaseModel

from vibepy_core import ErrorCategory
from vibepy_studio.models import Diagnostic


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


class InspectedTool(BaseModel):
    """One Tool a project declares."""

    name: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]


class InspectedPage(BaseModel):
    """One Page a project declares."""

    name: str
    route: str
    title: str


class InspectedApp(BaseModel):
    """One App a project declares, as its own environment describes it."""

    app_name: str
    distribution: str
    distribution_version: str
    app_id: str
    name: str
    version: str
    config_schema: dict[str, object]
    tools: list[InspectedTool]
    pages: list[InspectedPage]


class AppInspection(BaseModel):
    """What a project declares, or why that could not be read."""

    apps: list[InspectedApp]
    diagnostic: Diagnostic | None = None


class InvokeRequest(BaseModel):
    """One Tool of one App a project declares, with the App's configuration and the Tool's input."""

    project: Path
    app: str
    tool: str
    input: dict[str, object] = {}
    config: dict[str, object] = {}


class Invocation(BaseModel):
    """What the Tool returned, or why it did not."""

    output: dict[str, object] | None = None
    diagnostic: Diagnostic | None = None
