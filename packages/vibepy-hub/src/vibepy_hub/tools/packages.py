"""Offering the Apps of a local folder, and withdrawing that offer."""

from collections.abc import Sequence

from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import HubDeps, HubState, candidates, read_state, write_state
from vibepy_hub.models import CandidateRow, Diagnostic, SourceListing, SourcePath


def _listing(deps: HubDeps, /) -> SourceListing:
    """Every registered folder and what it offers."""
    state = read_state(deps.root)
    rows: list[CandidateRow] = []
    for source in state.sources:
        rows.extend(
            CandidateRow(
                folder=row.folder,
                name=row.name,
                version=row.version,
                declares_app=row.declares_app,
            )
            for row in candidates(source)
        )
    return SourceListing(sources=state.sources, candidates=rows)


async def register_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    """Offer the Apps in a local folder for installation."""
    deps = ctx.dependencies
    state = read_state(deps.root)
    if not payload.path.is_dir():
        return SourceListing(
            sources=state.sources,
            candidates=[],
            diagnostic=Diagnostic(
                code="hub.source_unreadable",
                message=f"{payload.path} is not a folder",
                details={"path": str(payload.path)},
            ),
        )
    if payload.path not in state.sources:
        write_state(
            deps.root, HubState(sources=[*state.sources, payload.path], config=state.config)
        )
    return _listing(deps)


async def remove_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    """Stop offering the Apps in a local folder."""
    deps = ctx.dependencies
    state = read_state(deps.root)
    write_state(
        deps.root,
        HubState(
            sources=[path for path in state.sources if path != payload.path],
            config=state.config,
        ),
    )
    return _listing(deps)


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
