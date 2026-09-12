"""Offering the Apps of a local folder, and withdrawing that offer."""

from collections.abc import Sequence
from pathlib import Path

from vibepy_core.channel import Channel
from vibepy_core.errors import ErrorCategory, ErrorInfo
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.internals import StudioDeps
from vibepy_studio.models import Empty
from vibepy_studio.operating.internals import (
    candidates,
    readable,
)
from vibepy_studio.operating.models import CandidateRow, SourceListing, SourcePath


async def _listing(deps: StudioDeps, /) -> SourceListing:
    """Return the registered source and what it offers.

    A source that can no longer be read is reported here as `list_apps` reports
    it. One fact, one answer: a Tool that stayed silent about it would contradict
    the other about the same source.
    """
    state = await deps.root.state()
    if state.source is None:
        return SourceListing(source=None, candidates=[])
    if not await readable(state.source):
        return SourceListing(
            source=state.source, candidates=[], diagnostic=_unreadable(state.source)
        )
    return SourceListing(
        source=state.source,
        candidates=[
            CandidateRow(
                wheel=row.wheel, name=row.name, version=row.version, declares_app=row.declares_app
            )
            for row in await candidates(state.source)
        ],
    )


def _unreadable(path: Path, /) -> ErrorInfo:
    """Describe a source this Hub could not read, named so a caller can replace it."""
    return ErrorInfo(
        code="hub.source_unreadable",
        category=ErrorCategory.CALLER,
        message=f"{path} is not a folder",
        details={"path": str(path)},
    )


async def register_package_source(
    ctx: ToolContext[StudioDeps], payload: SourcePath
) -> SourceListing:
    """Offer the wheels in a local folder for installation, replacing the folder before it."""
    deps = ctx.dependencies
    if not await readable(payload.path):
        state = await deps.root.state()
        return SourceListing(
            source=state.source, candidates=[], diagnostic=_unreadable(payload.path)
        )
    await deps.root.update_state(lambda held: held.model_copy(update={"source": payload.path}))
    return await _listing(deps)


async def remove_package_source(ctx: ToolContext[StudioDeps], _payload: Empty) -> SourceListing:
    """Stop offering wheels for installation. Installed Apps are unchanged."""
    await ctx.dependencies.root.update_state(lambda held: held.model_copy(update={"source": None}))
    return await _listing(ctx.dependencies)


PACKAGE_SOURCE_TOOLS: Sequence[Tool[StudioDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="register_package_source",
            description="Offer the wheels in a local folder for installation",
            input_model=SourcePath,
            output_model=SourceListing,
            read_only=False,
            channels=frozenset({Channel.WEB}),
        ),
        handler=register_package_source,
    ),
    Tool(
        definition=ToolDefinition(
            name="remove_package_source",
            description="Stop offering wheels for installation",
            input_model=Empty,
            output_model=SourceListing,
            read_only=False,
            channels=frozenset({Channel.WEB}),
        ),
        handler=remove_package_source,
    ),
]
