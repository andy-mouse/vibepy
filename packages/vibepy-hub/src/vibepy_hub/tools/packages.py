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
    """Every registered folder and what it offers.

    A registered source that can no longer be read is reported here as
    `list_apps` reports it. One fact, one answer: a Tool that stayed silent
    about it would contradict the other about the same source.
    """
    state = await read_state(deps.root)
    rows: list[CandidateRow] = []
    unreadable: list[str] = []
    for source in state.sources:
        if not await readable(source):
            unreadable.append(str(source))
            continue
        rows.extend(
            CandidateRow(
                folder=row.wheel,
                name=row.name,
                version=row.version,
                declares_app=row.declares_app,
            )
            for row in await candidates(source)
        )
    return SourceListing(
        sources=state.sources,
        candidates=rows,
        diagnostic=None if not unreadable else _unreadable(unreadable),
    )


def _unreadable(paths: Sequence[str], /) -> Diagnostic:
    """Describe registered sources this Hub could not read, named so a caller can withdraw one."""
    return Diagnostic(
        code="hub.source_unreadable",
        category=ErrorCategory.CALLER,
        message="a registered source could not be read",
        details={"paths": ", ".join(paths)},
    )


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

    def offer(held: HubState) -> HubState:
        """Make the decision inside the change, not before it.

        A membership test made against a state read earlier is a check whose
        answer a second caller can invalidate, which is the shape
        `update_state` exists to remove.
        """
        if payload.path in held.sources:
            return held
        return held.model_copy(update={"sources": [*held.sources, payload.path]})

    await update_state(deps, offer)
    return await _listing(deps)


async def remove_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    """Stop offering the Apps in a local folder."""
    deps = ctx.dependencies

    def withdraw(held: HubState) -> HubState:
        return held.model_copy(
            update={"sources": [path for path in held.sources if path != payload.path]}
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
