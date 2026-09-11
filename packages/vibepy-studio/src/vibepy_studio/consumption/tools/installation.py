"""Installing an App into an environment of its own, and removing it again.

An installed App is read from the file system rather than from a record the Hub
keeps: each App has an environment of its own, and `discover_apps(path=…)` reads
one without importing it.
"""

import logging
from collections.abc import Sequence

from packaging.utils import canonicalize_name
from packaging.version import Version

from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.consumption.internals import (
    Candidate,
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
    installed_facts,
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
from vibepy_studio.consumption.models import (
    AppListing,
    AppName,
    AppRow,
    Installation,
)
from vibepy_studio.internals import StudioDeps
from vibepy_studio.models import Diagnostic, Empty

logger = logging.getLogger(__name__)


async def _offered(deps: StudioDeps, app_name: str, /) -> Candidate | None:
    """Return the wheel the registered source offers under this name, or nothing."""
    source = (await read_state(deps.root)).source
    if source is None or not await readable(source):
        return None
    return next((row for row in await candidates(source) if row.name == app_name), None)


async def _installed(deps: StudioDeps, /) -> dict[str, AppRow]:
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
            distribution_version=facts.distribution_version,
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


async def install_app(ctx: ToolContext[StudioDeps], payload: AppName) -> Installation:
    """Install one offered App into an environment of its own."""
    deps = ctx.dependencies
    offered = await _offered(deps, payload.app_name)
    if offered is None:
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.candidate_absent",
                category=ErrorCategory.CALLER,
                message=f"The registered source offers no {payload.app_name!r}",
                details={"app_name": payload.app_name},
            ),
        )
    env = environment(deps.root, payload.app_name)
    if env in await environments(deps.root):
        # Installing over an installation is refused rather than given a meaning
        # of its own: `update_app` is the operation that remakes an environment
        # while keeping what the Hub holds, and `remove_app` is the one that
        # discards it.
        return Installation(
            app=AppRow(app_name=payload.app_name, state="installed"),
            diagnostic=Diagnostic(
                code="hub.already_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is already installed; remove it first",
                details={"app_name": payload.app_name},
            ),
        )
    if not offered.declares_app:
        return Installation(
            app=AppRow(
                app_name=payload.app_name, state="available", distribution_version=offered.version
            ),
            diagnostic=Diagnostic(
                code="hub.no_app_declared",
                category=ErrorCategory.DECLARATION,
                message=f"{offered.wheel.name} declares no App",
                details={"wheel": str(offered.wheel)},
            ),
        )
    return await _install_offered(deps, payload.app_name, offered)


async def _install_offered(deps: StudioDeps, app_name: str, offered: Candidate, /) -> Installation:
    """Create the environment, describe it, keep its facts, give it an address.

    Shared by installing and updating: an update is this, over an environment that
    was removed while the Hub kept everything else it held for the App.
    """
    env = environment(deps.root, app_name)
    try:
        await install(wheel=offered.wheel, source=offered.wheel.parent, env=env)
        described = await describe(env)
        metadata = await purelib(env)
        mine = [
            facts for facts in described if str(canonicalize_name(facts.distribution)) == app_name
        ]
        if not mine:
            await remove_environment(env)
            return Installation(
                app=AppRow(app_name=app_name, state="available"),
                diagnostic=Diagnostic(
                    code="hub.no_app_declared",
                    category=ErrorCategory.DECLARATION,
                    message=f"{offered.wheel} installs no App",
                    details={"wheel": str(offered.wheel)},
                ),
            )
        if len(mine) > 1:
            await remove_environment(env)
            return Installation(
                app=AppRow(app_name=app_name, state="available"),
                diagnostic=Diagnostic(
                    code="hub.multiple_apps_declared",
                    category=ErrorCategory.DECLARATION,
                    message=f"{app_name!r} declares more than one App",
                    details={
                        "app_name": app_name,
                        "declared": ", ".join(sorted(facts.declared_name for facts in mine)),
                    },
                ),
            )
        facts = mine[0].model_copy(update={"purelib": metadata})
        await write_facts(env, facts)
    except InstallFailed as failure:
        await remove_environment(env)
        return Installation(
            app=AppRow(app_name=app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.install_failed",
                category=ErrorCategory.EXECUTION,
                message=str(failure),
                details={"step": failure.step, "output": failure.output},
            ),
        )

    # An address is for an App that can answer at one. An App declaring no Pages has no Web channel
    # at all and `start_app` refuses it, so giving it a port and a route would publish an address
    # that is not slow to answer but will never answer, and point the proxy at a port nothing will
    # bind.
    if facts.has_pages:

        def hold(state: HubState) -> HubState:
            if app_name in state.ports:
                return state
            return state.model_copy(
                update={"ports": {**state.ports, app_name: allocate(state.ports.values())}}
            )

        port = (await update_state(deps, hold)).ports[app_name]
        await write_route(deps.root, app_name, port=port)
    return Installation(
        app=AppRow(
            app_name=app_name,
            name=facts.name,
            version=facts.version,
            distribution_version=facts.distribution_version,
            state="installed",
            url=address(app_name, deps.proxy_port) if facts.has_pages else None,
            has_pages=facts.has_pages,
        )
    )


async def list_apps(ctx: ToolContext[StudioDeps], _payload: Empty) -> AppListing:
    """Return every App this Hub can act on, installed or merely offered.

    An installed row's `distribution_version` is the version it runs at;
    `available_version` is set only when the source offers a different one, which
    is what `update_app` would install.
    """
    deps = ctx.dependencies
    rows = await _installed(deps)
    source = (await read_state(deps.root)).source
    unreadable = source is not None and not await readable(source)
    if source is not None and not unreadable:
        for row in await candidates(source):
            if not row.declares_app:
                # The wheelhouse also carries the framework and its dependencies,
                # resolved via `--find-links`; those are not Apps to offer.
                continue
            held = rows.get(row.name)
            if held is not None:
                if held.distribution_version is not None and Version(row.version) > Version(
                    held.distribution_version
                ):
                    rows[row.name] = held.model_copy(update={"available_version": row.version})
                continue
            rows[row.name] = AppRow(
                app_name=row.name,
                name=row.name,
                distribution_version=row.version,
                state="available",
            )
    return AppListing(
        apps=[rows[name] for name in sorted(rows)],
        source=source,
        diagnostic=None
        if not unreadable
        else Diagnostic(
            code="hub.source_unreadable",
            category=ErrorCategory.CALLER,
            message="the registered source could not be read",
            details={"path": str(source)},
        ),
    )


async def remove_app(ctx: ToolContext[StudioDeps], payload: AppName) -> AppListing:
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


async def update_app(ctx: ToolContext[StudioDeps], payload: AppName) -> Installation:
    """Replace an installed App with the version its source offers, keeping what the Hub holds.

    Configuration values, the port, the route and the data the App wrote elsewhere
    all survive: only the environment is remade. A running App is refused rather
    than restarted, because a restart policy is a decision this Tool does not own,
    and the user has Stop.
    """
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return _refused(
            payload.app_name,
            "hub.not_installed",
            f"{payload.app_name!r} is not installed",
            state="available",
        )
    if deps.processes.running(payload.app_name):
        return _refused(
            payload.app_name,
            "hub.already_running",
            f"{payload.app_name!r} is running; stop it first",
            state="running",
            version=facts.distribution_version,
        )
    offered = await _offered(deps, payload.app_name)
    if offered is None:
        return _refused(
            payload.app_name,
            "hub.candidate_absent",
            f"The registered source offers no {payload.app_name!r}",
            state="installed",
            version=facts.distribution_version,
        )
    if Version(offered.version) <= Version(facts.distribution_version):
        return _refused(
            payload.app_name,
            "hub.up_to_date",
            f"the offered version {offered.version} is not newer than "
            f"{facts.distribution_version}, which is already installed",
            state="installed",
            version=facts.distribution_version,
        )
    await remove_environment(environment(deps.root, payload.app_name))
    return await _install_offered(deps, payload.app_name, offered)


def _refused(
    app_name: str, code: str, message: str, /, *, state: str, version: str | None = None
) -> Installation:
    """Say an update did not happen, and why. Every refusal here is the caller's to act on."""
    return Installation(
        app=AppRow(app_name=app_name, state=state, distribution_version=version),
        diagnostic=Diagnostic(
            code=code,
            category=ErrorCategory.CALLER,
            message=message,
            details={"app_name": app_name},
        ),
    )


INSTALLATION_TOOLS: Sequence[Tool[StudioDeps]] = [
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
    Tool(
        definition=ToolDefinition(
            name="update_app",
            description="Replace an installed App with the version its source offers",
            input_model=AppName,
            output_model=Installation,
        ),
        handler=update_app,
    ),
]
