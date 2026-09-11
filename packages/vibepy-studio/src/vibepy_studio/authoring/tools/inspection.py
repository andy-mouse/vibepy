"""Describing the framework, and describing what a project declares."""

import logging
from collections.abc import Sequence
from importlib.metadata import version

from vibepy_core import APP_GROUP, ERROR_CATALOG
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.models import ErrorCode, FrameworkDescription
from vibepy_studio.internals import StudioDeps
from vibepy_studio.models import Empty

logger = logging.getLogger(__name__)

CHANNEL_EXTRAS = ["web", "agent"]
"""The extras of `vibepy-core` that carry a channel; `docs/architecture/packaging.md`
owns the fact."""


async def inspect_framework(_ctx: ToolContext[StudioDeps], _payload: Empty) -> FrameworkDescription:
    """Say what the framework this Studio is built on asserts about itself."""
    return FrameworkDescription(
        framework_version=version("vibepy-core"),
        entry_point_group=APP_GROUP,
        channel_extras=list(CHANNEL_EXTRAS),
        error_catalog=[ErrorCode(code=code, category=cat) for code, cat in ERROR_CATALOG.items()],
    )


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
]
