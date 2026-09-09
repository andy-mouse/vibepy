"""Installing an App into an environment of its own, and removing it again.

An installed App is read from the file system rather than from a record the Hub
keeps: each App has an environment of its own, and `discover_apps(path=…)` reads
one without importing it.
"""

import logging
from collections.abc import Sequence

from packaging.utils import canonicalize_name

from vibepy_core.app.package import discover_apps
from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import (
    Candidate,
    HubDeps,
    HubState,
    InstallFailed,
    candidates,
    describe,
    environment,
    environments,
    install,
    is_configured,
    purelib,
    read_facts,
    read_state,
    readable,
    remove_environment,
    update_state,
    write_facts,
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


async def _candidate(deps: HubDeps, app_name: str, /) -> Candidate | None:
    """The registered folder that offers this App, by its distribution name."""
    for source in (await read_state(deps.root)).sources:
        for row in await candidates(source):
            if row.name == app_name:
                return row
    return None


async def _installed(deps: HubDeps, /) -> dict[str, AppRow]:
    """One row per environment this Hub created, read without importing."""
    rows: dict[str, AppRow] = {}
    held = (await read_state(deps.root)).config
    for env in await environments(deps.root):
        facts = await read_facts(env)
        if facts is None or facts.purelib is None:
            rows[env.name] = AppRow(
                app_name=env.name,
                state="installed",
                diagnostic=Diagnostic(
                    code="hub.facts_unreadable",
                    category=ErrorCategory.EXECUTION,
                    message=f"{env} holds no readable record of what was installed",
                    details={"app_name": env.name},
                ),
            )
            continue
        metadata = facts.purelib
        declared = discover_apps(path=[metadata])
        wanted = facts.declared_name
        present = any(
            ref.app_name == wanted and ref.distribution == facts.distribution for ref in declared
        )
        port = deps.processes.running(env.name)
        rows[env.name] = AppRow(
            app_name=env.name,
            name=facts.name,
            version=facts.version,
            state="running" if port is not None else "installed",
            url=f"http://127.0.0.1:{port}" if port is not None else None,
            configured=is_configured(facts, held.get(env.name, {})),
            has_pages=facts.has_pages,
            diagnostic=None
            if present
            else Diagnostic(
                code="hub.declaration_missing",
                category=ErrorCategory.DECLARATION,
                message=f"{env} no longer declares {wanted!r}",
                details={"app_name": env.name, "declared_name": wanted},
            ),
        )
    return rows


async def install_app(ctx: ToolContext[HubDeps], payload: AppName) -> Installation:
    """Install one offered App into an environment of its own."""
    deps = ctx.dependencies
    offered = await _candidate(deps, payload.app_name)
    if offered is None:
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.candidate_absent",
                category=ErrorCategory.CALLER,
                message=f"No registered source offers {payload.app_name!r}",
                details={"app_name": payload.app_name},
            ),
        )
    folder = offered.folder
    env = environment(deps.root, payload.app_name)
    try:
        await install(folder=folder, env=env)
        described = await describe(env)
        metadata = await purelib(env)
        mine = [
            facts
            for facts in described
            if str(canonicalize_name(facts.distribution)) == payload.app_name
        ]
        if not mine:
            await remove_environment(env)
            return Installation(
                app=AppRow(app_name=payload.app_name, state="available"),
                diagnostic=Diagnostic(
                    code="hub.no_app_declared",
                    category=ErrorCategory.DECLARATION,
                    message=f"{folder} installs no App",
                    details={"folder": str(folder)},
                ),
            )
        if len(mine) > 1:
            await remove_environment(env)
            return Installation(
                app=AppRow(app_name=payload.app_name, state="available"),
                diagnostic=Diagnostic(
                    code="hub.multiple_apps_declared",
                    category=ErrorCategory.DECLARATION,
                    message=f"{payload.app_name!r} declares more than one App",
                    details={
                        "app_name": payload.app_name,
                        "declared": ", ".join(sorted(facts.declared_name for facts in mine)),
                    },
                ),
            )
        facts = mine[0].model_copy(update={"purelib": metadata})
        await write_facts(env, facts)
    except InstallFailed as failure:
        await remove_environment(env)
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.install_failed",
                category=ErrorCategory.EXECUTION,
                message=str(failure),
                details={"step": failure.step, "output": failure.output},
            ),
        )
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
    unreadable: list[str] = []
    for source in (await read_state(deps.root)).sources:
        if not await readable(source):
            unreadable.append(str(source))
            continue
        for row in await candidates(source):
            if row.name in rows:
                continue
            rows[row.name] = AppRow(
                app_name=row.name,
                name=row.name,
                version=row.version,
                state="available",
            )
    return AppListing(
        apps=[rows[name] for name in sorted(rows)],
        diagnostic=None
        if not unreadable
        else Diagnostic(
            code="hub.source_unreadable",
            category=ErrorCategory.CALLER,
            message="a registered source could not be read",
            details={"paths": ", ".join(unreadable)},
        ),
    )


async def remove_app(ctx: ToolContext[HubDeps], payload: AppName) -> AppListing:
    """Delete an App's environment, leaving the data it wrote elsewhere."""
    deps = ctx.dependencies
    await deps.processes.stop(payload.app_name)
    await remove_environment(environment(deps.root, payload.app_name))

    def forget(state: HubState) -> HubState:
        return HubState(
            sources=state.sources,
            config={
                name: values for name, values in state.config.items() if name != payload.app_name
            },
        )

    await update_state(deps, forget)
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
