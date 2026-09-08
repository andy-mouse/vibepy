"""Installing an App into an environment of its own, and removing it again.

An installed App is read from the file system rather than from a record the Hub
keeps: each App has an environment of its own, and `discover_apps(path=…)` reads
one without importing it.
"""

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

from vibepy.app.package import discover_apps
from vibepy.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import (
    HubDeps,
    HubState,
    InstallFailed,
    candidates,
    describe,
    environment,
    install,
    is_configured,
    purelib,
    read_facts,
    read_state,
    write_facts,
    write_state,
)
from vibepy_hub.models import (
    AppListing,
    AppName,
    AppRow,
    Diagnostic,
    Empty,
    Installation,
)

logger = logging.getLogger(__name__)


def _candidate_folder(deps: HubDeps, app_name: str, /) -> Path | None:
    """The registered folder that offers this App, by project or folder name."""
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            if app_name in {row.name, row.folder.name}:
                return row.folder
    return None


async def _installed(deps: HubDeps, /) -> dict[str, AppRow]:
    """One row per environment this Hub created, read without importing."""
    envs = deps.root / "envs"
    rows: dict[str, AppRow] = {}
    if not envs.is_dir():
        return rows
    held = read_state(deps.root).config
    for env in sorted(path for path in envs.iterdir() if path.is_dir()):
        facts = read_facts(env)
        metadata = facts.purelib if facts and facts.purelib else await purelib(env)
        declared = discover_apps(path=[metadata])
        wanted = facts.declared_name if facts else env.name
        present = any(ref.app_name == wanted for ref in declared)
        port = deps.processes.running(env.name)
        rows[env.name] = AppRow(
            app_name=env.name,
            name=facts.name if facts else None,
            version=facts.version if facts else None,
            state="running" if port is not None else "installed",
            url=f"http://127.0.0.1:{port}" if port is not None else None,
            configured=bool(facts and is_configured(facts, held.get(env.name, {}))),
            has_pages=bool(facts and facts.has_pages),
            diagnostic=None
            if present
            else Diagnostic(
                code="hub.declaration_missing",
                message=f"{env} no longer declares {wanted!r}",
                details={"app_name": env.name, "declared_name": wanted},
            ),
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
    metadata = await purelib(env)
    declared = discover_apps(path=[metadata])
    found = next(iter(described), None)
    if found is None or not declared:
        shutil.rmtree(env, ignore_errors=True)
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.no_app_declared",
                message=f"{folder} installs no App",
                details={"folder": str(folder)},
            ),
        )
    facts = found.model_copy(update={"purelib": metadata, "declared_name": declared[0].app_name})
    write_facts(env, facts)
    return Installation(
        app=AppRow(
            app_name=payload.app_name,
            name=facts.name,
            version=facts.version,
            state="installed",
            has_pages=facts.has_pages,
        )
    )


async def list_apps(ctx: ToolContext[HubDeps], _payload: Empty) -> AppListing:
    """Every App this Hub can act on, installed or merely offered."""
    deps = ctx.dependencies
    rows = await _installed(deps)
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
    await deps.processes.stop(payload.app_name)
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


INSTALLATION_TOOLS: Sequence[Tool[HubDeps]] = [
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
