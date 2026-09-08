"""The Hub's public operations.

Each Tool is one affordance of the control plane. The work they call — reading a
folder, reading and writing the state file — is domain internals and is not
published as a Tool.
"""

import logging
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vibepy.app.package import discover_apps
from vibepy.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.installer import (
    InstallFailed,
    describe,
    environment,
    install,
    interpreter,
    purelib,
    read_facts,
    write_facts,
)
from vibepy_hub.internals import HubDeps
from vibepy_hub.models import (
    AppFacts,
    AppListing,
    AppName,
    AppRow,
    CandidateRow,
    ConfigureRequest,
    Diagnostic,
    Empty,
    HeldConfig,
    Installation,
    RunningApp,
    SourceListing,
    SourcePath,
    StartRequest,
)
from vibepy_hub.processes import StartFailed
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
            configured=env.name in held,
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


class _SchemaField(BaseModel):
    """One property of a projected configuration schema, as the Hub reads it."""

    format: str | None = None


class _ConfigSchema(BaseModel):
    """As much of a JSON Schema as telling a secret from a string requires."""

    properties: dict[str, _SchemaField] = {}


def secret_fields(schema: Mapping[str, object], /) -> tuple[str, ...]:
    """The fields an App declared as secret, read from its projected schema.

    Pydantic projects `SecretStr` as `format: password`, so a Host tells a secret
    from an ordinary string without importing the App. See
    `docs/decisions/ADR-022-configuration-is-a-declaration.md`.
    """
    try:
        described = _ConfigSchema.model_validate(dict(schema))
    except ValidationError:
        logger.info("unreadable configuration schema")
        return ()
    return tuple(name for name, field in described.properties.items() if field.format == "password")


def _facts(deps: HubDeps, app_name: str, /) -> AppFacts | None:
    """What an installed App declared, or nothing when it is not installed."""
    env = environment(deps.root, app_name)
    return read_facts(env) if env.is_dir() else None


async def configure_app(ctx: ToolContext[HubDeps], payload: ConfigureRequest) -> HeldConfig:
    """Hold the values one App runs with, excluding the secrets it declared.

    The Hub does not validate them: the App's own window validates configuration
    as it opens and raises `config.invalid`.
    """
    deps = ctx.dependencies
    facts = _facts(deps, payload.app_name)
    if facts is None:
        return HeldConfig(
            app_name=payload.app_name,
            values={},
            required_secrets=[],
            diagnostic=Diagnostic(
                code="hub.not_installed",
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts.config_schema)
    kept = {name: value for name, value in payload.values.items() if name not in secrets}
    state = read_state(deps.root)
    write_state(
        deps.root,
        HubState(sources=state.sources, config={**state.config, payload.app_name: kept}),
    )
    return HeldConfig(app_name=payload.app_name, values=kept, required_secrets=list(secrets))


def _refusal(app_name: str, code: str, message: str, /) -> RunningApp:
    """An App that will not start or stop, and why."""
    return RunningApp(
        app_name=app_name,
        state="installed",
        diagnostic=Diagnostic(code=code, message=message, details={"app_name": app_name}),
    )


async def start_app(ctx: ToolContext[HubDeps], payload: StartRequest) -> RunningApp:
    """Open one installed App's Web channel on a port of its own."""
    deps = ctx.dependencies
    facts = _facts(deps, payload.app_name)
    if facts is None:
        return _refusal(
            payload.app_name, "hub.not_installed", f"{payload.app_name!r} is not installed"
        )
    if not facts.has_pages:
        return _refusal(
            payload.app_name,
            "hub.no_web_channel",
            f"{payload.app_name!r} declares no Pages, so it has no Web channel to start",
        )
    if deps.processes.running(payload.app_name) is not None:
        return _refusal(
            payload.app_name, "hub.already_running", f"{payload.app_name!r} is already running"
        )
    held = read_state(deps.root).config.get(payload.app_name, {})
    try:
        port = await deps.processes.start(
            app_name=facts.declared_name,
            interpreter=interpreter(environment(deps.root, payload.app_name)),
            config={**held, **payload.secrets},
            known_as=payload.app_name,
        )
    except StartFailed as failure:
        return _refusal(payload.app_name, "hub.start_failed", str(failure))
    return RunningApp(app_name=payload.app_name, url=f"http://127.0.0.1:{port}", state="running")


async def stop_app(ctx: ToolContext[HubDeps], payload: AppName) -> RunningApp:
    """Stop an App this window started."""
    if not await ctx.dependencies.processes.stop(payload.app_name):
        return _refusal(
            payload.app_name, "hub.not_running", f"{payload.app_name!r} is not running here"
        )
    return RunningApp(app_name=payload.app_name, state="installed")


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
            name="configure_app",
            description="Hold the values an App runs with",
            input_model=ConfigureRequest,
            output_model=HeldConfig,
        ),
        handler=configure_app,
    ),
    Tool(
        definition=ToolDefinition(
            name="start_app",
            description="Open an installed App's Web channel",
            input_model=StartRequest,
            output_model=RunningApp,
        ),
        handler=start_app,
    ),
    Tool(
        definition=ToolDefinition(
            name="stop_app",
            description="Stop an App this Hub started",
            input_model=AppName,
            output_model=RunningApp,
        ),
        handler=stop_app,
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
