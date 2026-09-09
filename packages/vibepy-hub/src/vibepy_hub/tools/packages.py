"""Offering the Apps of a local folder, and withdrawing that offer."""

from collections.abc import Sequence

from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import (
    HubDeps,
    HubState,
    candidates,
    read_state,
    readable,
    update_state,
)
from vibepy_hub.models import CandidateRow, Diagnostic, SourceListing, SourcePath


async def _listing(deps: HubDeps, /) -> SourceListing:
    """Every registered folder and what it offers."""
    state = await read_state(deps.root)
    rows: list[CandidateRow] = []
    for source in state.sources:
        rows.extend(
            CandidateRow(
                folder=row.folder,
                name=row.name,
                version=row.version,
                declares_app=row.declares_app,
            )
            for row in await candidates(source)
        )
    return SourceListing(sources=state.sources, candidates=rows)


async def register_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    """Offer the Apps in a local folder for installation."""
    deps = ctx.dependencies
    state = await read_state(deps.root)
    if not await readable(payload.path):
        return SourceListing(
            sources=state.sources,
            candidates=[],
            diagnostic=Diagnostic(
                code="hub.source_unreadable",
                category=ErrorCategory.CALLER,
                message=f"{payload.path} is not a folder",
                details={"path": str(payload.path)},
            ),
        )
    if payload.path not in state.sources:

        def offer(held: HubState) -> HubState:
            return HubState(sources=[*held.sources, payload.path], config=held.config)

        await update_state(deps, offer)
    return await _listing(deps)


async def remove_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    """Stop offering the Apps in a local folder."""
    deps = ctx.dependencies

    def withdraw(held: HubState) -> HubState:
        return HubState(
            sources=[path for path in held.sources if path != payload.path],
            config=held.config,
        )

    await update_state(deps, withdraw)
    return await _listing(deps)


PACKAGE_SOURCE_TOOLS: Sequence[Tool[HubDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="register_package_source",
            description="Offer the Apps in a local folder for installation",
            input_model=SourcePath,
            output_model=SourceListing,
        ),
        handler=register_package_source,
    ),
    Tool(
        definition=ToolDefinition(
            name="remove_package_source",
            description="Stop offering the Apps in a local folder",
            input_model=SourcePath,
            output_model=SourceListing,
        ),
        handler=remove_package_source,
    ),
]
