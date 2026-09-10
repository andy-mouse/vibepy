"""Installing an App into an environment of its own, and removing it again.

An installed App is read from the file system rather than from a record the Hub
keeps: each App has an environment of its own, and `discover_apps(path=…)` reads
one without importing it.
"""

import logging
from collections.abc import Sequence

from packaging.utils import canonicalize_name

from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import (
    Candidate,
    HubDeps,
    HubState,
    InstallFailed,
    address,
    allocate,
    candidates,
    declarations,
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
    remove_route,
    update_state,
    write_facts,
    write_route,
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


async def _offering(deps: HubDeps, app_name: str, /) -> tuple[Candidate, ...]:
    """Every registered folder that offers this App, by its distribution name.

    More than one is not a preference to resolve. One name addresses one App,
    and letting registration order decide which folder a name means would put
    back the ambiguity this Hub addresses Apps by a canonical name to remove.
    """
    found: list[Candidate] = []
    for source in (await read_state(deps.root)).sources:
        found.extend(row for row in await candidates(source) if row.name == app_name)
    return tuple(found)


def _ambiguous(app_name: str, offered: Sequence[Candidate], /) -> Diagnostic:
    """Two folders claiming one name, named so a caller can withdraw one."""
    return Diagnostic(
        code="hub.candidate_ambiguous",
        category=ErrorCategory.CALLER,
        message=f"more than one registered source offers {app_name!r}",
        details={
            "app_name": app_name,
            "folders": ", ".join(sorted(str(row.folder) for row in offered)),
        },
    )


async def _installed(deps: HubDeps, /) -> dict[str, AppRow]:
    """One row per environment this Hub created, read without importing."""
    rows: dict[str, AppRow] = {}
    stored = await read_state(deps.root)
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
        declared = await declarations(metadata)
        wanted = facts.declared_name
        present = any(
            ref.app_name == wanted and ref.distribution == facts.distribution for ref in declared
        )
        held_port = stored.ports.get(env.name)
        rows[env.name] = AppRow(
            app_name=env.name,
            name=facts.name,
            version=facts.version,
            state="running" if deps.processes.running(env.name) else "installed",
            url=None if held_port is None else address(env.name, deps.proxy_port),
            configured=is_configured(facts, stored.config.get(env.name, {})),
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
    offered = await _offering(deps, payload.app_name)
    if len(offered) != 1:
        # Neither none nor two is one App to install, and a caller answers the
        # two differently: register a source, or withdraw one.
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.candidate_absent",
                category=ErrorCategory.CALLER,
                message=f"No registered source offers {payload.app_name!r}",
                details={"app_name": payload.app_name},
            )
            if not offered
            else _ambiguous(payload.app_name, offered),
        )
    folder = offered[0].folder
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

    def hold(state: HubState) -> HubState:
        return state.model_copy(
            update={
                "ports": {
                    **state.ports,
                    payload.app_name: allocate(state.ports, payload.app_name),
                }
            }
        )

    port = (await update_state(deps, hold)).ports[payload.app_name]
    await write_route(deps.root, payload.app_name, port=port)
    return Installation(
        app=AppRow(
            app_name=payload.app_name,
            name=facts.name,
            version=facts.version,
            state="installed",
            url=address(payload.app_name, deps.proxy_port),
            has_pages=facts.has_pages,
        )
    )


async def list_apps(ctx: ToolContext[HubDeps], _payload: Empty) -> AppListing:
    """Every App this Hub can act on, installed or merely offered."""
    deps = ctx.dependencies
    rows = await _installed(deps)
    offered: dict[str, list[Candidate]] = {}
    unreadable: list[str] = []
    for source in (await read_state(deps.root)).sources:
        if not await readable(source):
            unreadable.append(str(source))
            continue
        for row in await candidates(source):
            offered.setdefault(row.name, []).append(row)
            if row.name in rows:
                continue
            rows[row.name] = AppRow(
                app_name=row.name,
                name=row.name,
                version=row.version,
                state="available",
            )
    for name, claiming in offered.items():
        if len(claiming) > 1 and rows[name].state == "available":
            rows[name] = rows[name].model_copy(update={"diagnostic": _ambiguous(name, claiming)})
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
        return state.model_copy(
            update={
                "config": {
                    name: values
                    for name, values in state.config.items()
                    if name != payload.app_name
                },
                "ports": {
                    name: port for name, port in state.ports.items() if name != payload.app_name
                },
            }
        )

    await update_state(deps, forget)
    # After the state, so that a failure in between leaves a route to a child
    # that is gone -- which the proxy answers as 502 -- rather than a port held
    # by an App that no longer has one, which nothing would report at all.
    await remove_route(deps.root, payload.app_name)
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
