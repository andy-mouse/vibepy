"""Describing the framework, and describing what a project declares."""

import logging
from collections.abc import Sequence

from packaging.utils import canonicalize_name

from vibepy_core.app.group import APP_GROUP
from vibepy_core.channel import Channel
from vibepy_core.errors import ERROR_CATALOG
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import (
    declared_name,
    framework_version,
    locate,
    python,
)
from vibepy_studio.authoring.models import (
    AppInspection,
    ErrorCode,
    FrameworkDescription,
    InspectRequest,
    environment_failed,
    no_apps_declared,
    project_not_found,
    uv_unavailable,
)
from vibepy_studio.internals import DescribeFailed, NotRunnable, describe
from vibepy_studio.models import Empty, diagnostic_of

logger = logging.getLogger(__name__)

CHANNEL_EXTRAS = ["web", "agent"]
"""The extras of `vibepy-core` that carry a channel; `docs/architecture/packaging.md`
owns the fact."""


async def inspect_framework(_ctx: ToolContext[object], _payload: Empty) -> FrameworkDescription:
    """Say what the framework this Studio is built on asserts about itself."""
    return FrameworkDescription(
        framework_version=await framework_version(),
        entry_point_group=APP_GROUP,
        channel_extras=list(CHANNEL_EXTRAS),
        error_catalog=[ErrorCode(code=code, category=cat) for code, cat in ERROR_CATALOG.items()],
    )


async def inspect_app(_ctx: ToolContext[object], payload: InspectRequest) -> AppInspection:
    """Describe the Apps a source project declares, read in that project's environment."""
    project = await locate(payload.project)
    if project is None:
        return AppInspection(
            apps=[], diagnostics=[project_not_found(payload.project, "holds no pyproject.toml")]
        )
    name = await declared_name(project)
    if name is None:
        return AppInspection(
            apps=[], diagnostics=[project_not_found(project, "declares no [project] name")]
        )
    try:
        described = await describe(python(project))
    except NotRunnable:
        return AppInspection(apps=[], diagnostics=[uv_unavailable(project)])
    except DescribeFailed as failed:
        if failed.reports:
            return AppInspection(
                apps=[],
                diagnostics=[diagnostic_of(info, project=str(project)) for info in failed.reports],
            )
        return AppInspection(apps=[], diagnostics=[environment_failed(project, failed.output)])
    own = [entry for entry in described if canonicalize_name(entry.distribution) == name]
    if not own:
        return AppInspection(apps=[], diagnostics=[no_apps_declared(project, name)])
    return AppInspection(apps=own)


INSPECTION_TOOLS: Sequence[Tool[object]] = [
    Tool(
        definition=ToolDefinition(
            name="inspect_framework",
            description=(
                "What the framework asserts about itself: version, entry point group, "
                "channel extras, error catalogue"
            ),
            input_model=Empty,
            output_model=FrameworkDescription,
            read_only=True,
            channels=frozenset({Channel.AGENT}),
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
            read_only=True,
            channels=frozenset({Channel.AGENT}),
        ),
        handler=inspect_app,
    ),
]
