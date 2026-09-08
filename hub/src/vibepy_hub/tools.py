"""The Hub's public operations.

Each Tool is one affordance of the control plane. The work they call — reading a
folder, reading and writing the state file — is domain internals and is not
published as a Tool.
"""

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

from vibepy.app.package import discover_apps
from vibepy.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.installer import (
    InstallFailed,
    describe,
    environment,
    install,
    read_facts,
    site_packages,
    write_facts,
)
from vibepy_hub.internals import HubDeps
from vibepy_hub.models import (
    AppListing,
    AppName,
    AppRow,
    CandidateRow,
    Diagnostic,
    Empty,
    Installation,
    SourceListing,
    SourcePath,
)
from vibepy_hub.sources import candidates
from vibepy_hub.state import HubState, read_state, write_state

logger = logging.getLogger(__name__)


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


def _candidate_folder(deps: HubDeps, app_name: str, /) -> Path | None:
    """The registered folder that offers this App, by project or folder name."""
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            if app_name in {row.name, row.folder.name}:
                return row.folder
    return None


def _installed(deps: HubDeps, /) -> dict[str, AppRow]:
    """One row per environment this Hub created, read without importing."""
    envs = deps.root / "envs"
    rows: dict[str, AppRow] = {}
    if not envs.is_dir():
        return rows
    held = read_state(deps.root).config
    for env in sorted(path for path in envs.iterdir() if path.is_dir()):
        declared = discover_apps(path=[site_packages(env)])
        found = next((ref for ref in declared if ref.app_name == env.name), None)
        facts = read_facts(env)
        rows[env.name] = AppRow(
            app_name=env.name,
            name=facts.name if facts else None,
            version=found.distribution_version if found else None,
            state="installed",
            configured=env.name in held,
            has_pages=bool(facts and facts.has_pages),
        )
    return rows


async def install_app(ctx: ToolContext[HubDeps], payload: AppName) -> Installation:
    """Install one offered App into an environment of its own."""
    deps = ctx.dependencies
    folder = _candidate_folder(deps, payload.app_name)
    if folder is None:
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.candidate_absent",
                message=f"No registered source offers {payload.app_name!r}",
                details={"app_name": payload.app_name},
            ),
        )
    env = environment(deps.root, payload.app_name)
    try:
        await install(folder=folder, env=env)
        described = await describe(env)
    except InstallFailed as failure:
        shutil.rmtree(env, ignore_errors=True)
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.install_failed",
                message=str(failure),
                details={"step": failure.step, "output": failure.output},
            ),
        )
    facts = next((entry for entry in described if entry.name), None)
    if facts is not None:
        write_facts(env, facts)
    return Installation(
        app=AppRow(
            app_name=payload.app_name,
            name=facts.name if facts else None,
            version=facts.version if facts else None,
            state="installed",
            has_pages=bool(facts and facts.has_pages),
        )
    )


async def list_apps(ctx: ToolContext[HubDeps], _payload: Empty) -> AppListing:
    """Every App this Hub can act on, installed or merely offered."""
    deps = ctx.dependencies
    rows = _installed(deps)
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            app_name = row.folder.name
            if app_name in rows:
                continue
            rows[app_name] = AppRow(
                app_name=app_name,
                name=row.name,
                version=row.version,
                state="available",
            )
    return AppListing(apps=[rows[name] for name in sorted(rows)])


async def remove_app(ctx: ToolContext[HubDeps], payload: AppName) -> AppListing:
    """Delete an App's environment, leaving the data it wrote elsewhere."""
    deps = ctx.dependencies
    shutil.rmtree(environment(deps.root, payload.app_name), ignore_errors=True)
    state = read_state(deps.root)
    write_state(
        deps.root,
        HubState(
            sources=state.sources,
            config={
                name: values for name, values in state.config.items() if name != payload.app_name
            },
        ),
    )
    return await list_apps(ctx, Empty())


HUB_TOOLS: Sequence[Tool[HubDeps]] = [
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
    Tool(
        definition=ToolDefinition(
            name="list_apps",
            description="Every App this Hub can act on, with its state",
            input_model=Empty,
            output_model=AppListing,
        ),
        handler=list_apps,
    ),
    Tool(
        definition=ToolDefinition(
            name="install_app",
            description="Install an offered App into an environment of its own",
            input_model=AppName,
            output_model=Installation,
        ),
        handler=install_app,
    ),
    Tool(
        definition=ToolDefinition(
            name="remove_app",
            description="Remove an installed App, leaving the data it wrote",
            input_model=AppName,
            output_model=AppListing,
        ),
        handler=remove_app,
    ),
]
