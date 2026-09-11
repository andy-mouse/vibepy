"""Describing the framework, and describing what a project declares."""

import asyncio
import logging
from collections.abc import Sequence
from importlib.metadata import version

from packaging.utils import canonicalize_name

from vibepy_core.app.group import APP_GROUP
from vibepy_core.errors import ERROR_CATALOG
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import declared_name, locate, python
from vibepy_studio.authoring.models import (
    AppInspection,
    ErrorCode,
    FrameworkDescription,
    InspectRequest,
    from_report,
    no_apps_declared,
    project_not_found,
    uv_unavailable,
)
from vibepy_studio.internals import DescribeFailed, NotRunnable, StudioDeps, describe
from vibepy_studio.models import Empty

logger = logging.getLogger(__name__)

CHANNEL_EXTRAS = ["web", "agent"]
"""The extras of `vibepy-core` that carry a channel; `docs/architecture/packaging.md`
owns the fact."""


async def inspect_framework(_ctx: ToolContext[StudioDeps], _payload: Empty) -> FrameworkDescription:
    """Say what the framework this Studio is built on asserts about itself."""
    return FrameworkDescription(
        framework_version=await asyncio.to_thread(version, "vibepy-core"),
        entry_point_group=APP_GROUP,
        channel_extras=list(CHANNEL_EXTRAS),
        error_catalog=[ErrorCode(code=code, category=cat) for code, cat in ERROR_CATALOG.items()],
    )


async def inspect_app(_ctx: ToolContext[StudioDeps], payload: InspectRequest) -> AppInspection:
    """Describe the Apps a source project declares, read in that project's environment."""
    project = await asyncio.to_thread(locate, payload.project)
    if project is None:
        return AppInspection(
            apps=[], diagnostic=project_not_found(payload.project, "holds no pyproject.toml")
        )
    name = await asyncio.to_thread(declared_name, project)
    if name is None:
        return AppInspection(
            apps=[], diagnostic=project_not_found(project, "declares no [project] name")
        )
    try:
        described = await describe(python(project))
    except NotRunnable:
        return AppInspection(apps=[], diagnostic=uv_unavailable(project))
    except DescribeFailed as failed:
        return AppInspection(
            apps=[], diagnostic=from_report(project, failed.reported, failed.output)
        )
    own = [entry for entry in described if canonicalize_name(entry.distribution) == name]
    if not own:
        return AppInspection(apps=[], diagnostic=no_apps_declared(project, name))
    return AppInspection(apps=own)


INSPECTION_TOOLS: Sequence[Tool[StudioDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="inspect_framework",
            description=(
                "What the framework asserts about itself: version, entry point group, "
                "channel extras, error catalogue"
            ),
            input_model=Empty,
            output_model=FrameworkDescription,
        ),
        handler=inspect_framework,
    ),
    Tool(
        definition=ToolDefinition(
            name="inspect_app",
            description=(
                "Describe the Apps a source project declares, read in the project's own environment"
            ),
            input_model=InspectRequest,
            output_model=AppInspection,
        ),
        handler=inspect_app,
    ),
]
