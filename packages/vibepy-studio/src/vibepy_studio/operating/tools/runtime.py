"""Opening and closing an installed App's Web channel."""

from collections.abc import Sequence

from vibepy_core.channel import Channel
from vibepy_core.errors import ErrorCategory, ErrorInfo
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.internals import AlreadyStarted, StartFailed, StudioDeps
from vibepy_studio.models import diagnostic_of
from vibepy_studio.operating.internals import (
    address,
    environment,
    installed_facts,
    interpreter,
    read_state,
)
from vibepy_studio.operating.models import AppName, RunningApp, StartRequest


def _refusal(
    app_name: str,
    code: str,
    message: str,
    /,
    *,
    category: ErrorCategory,
    url: str | None = None,
) -> RunningApp:
    """Describe an App that will not start or stop, and why.

    It carries the App's address when it has one, because an address belongs to
    an installation rather than to a run: a refusal is not a reason to stop
    saying where an App lives.
    """
    return RunningApp(
        app_name=app_name,
        state="installed",
        url=url,
        diagnostic=ErrorInfo(
            code=code, category=category, message=message, details={"app_name": app_name}
        ),
    )


async def start_app(ctx: ToolContext[StudioDeps], payload: StartRequest) -> RunningApp:
    """Open one installed App's Web channel on a port of its own."""
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return _refusal(
            payload.app_name,
            "hub.not_installed",
            f"{payload.app_name!r} is not installed",
            category=ErrorCategory.CALLER,
        )
    if not facts.has_pages:
        return _refusal(
            payload.app_name,
            "hub.no_web_channel",
            f"{payload.app_name!r} declares no Pages, so it has no Web channel to start",
            category=ErrorCategory.CALLER,
        )
    state = await read_state(deps.root)
    held = state.config.get(payload.app_name, {})
    port = state.ports.get(payload.app_name)
    if port is None:
        # Installed, and holding no address. An App becomes installed when its
        # facts are written and is given a port after that, so a window that
        # closes between the two leaves this behind; so does a state file
        # written before an App had an address at all. Which of the two it was
        # is not knowable here and does not change the remedy, and it is not
        # `hub.not_installed`: the App is there, and installing is refused
        # until it is removed.
        return _refusal(
            payload.app_name,
            "hub.no_address",
            f"{payload.app_name!r} is installed but holds no address; "
            "remove it and install it again",
            category=ErrorCategory.CALLER,
        )
    where = address(payload.app_name, deps.proxy_port)
    try:
        await deps.processes.start(
            app_name=facts.described.app_name,
            interpreter=interpreter(environment(deps.root, payload.app_name)),
            config={**held, **payload.secrets},
            known_as=payload.app_name,
            port=port,
        )
    except AlreadyStarted:
        # One name holds one child, and `Processes` is the one place that
        # decides it: a check made here would not survive this handler's own
        # awaits, and two places deciding one fact is how they come to disagree.
        return _refusal(
            payload.app_name,
            "hub.already_running",
            f"{payload.app_name!r} is already running",
            category=ErrorCategory.CALLER,
            url=where,
        )
    except StartFailed as failure:
        reported = failure.reported
        if reported is None:
            return _refusal(
                payload.app_name,
                "hub.start_failed",
                str(failure),
                category=ErrorCategory.EXECUTION,
                url=where,
            )
        return RunningApp(
            app_name=payload.app_name,
            state="installed",
            url=where,
            diagnostic=diagnostic_of(reported, app_name=payload.app_name),
        )
    return RunningApp(app_name=payload.app_name, url=where, state="running")


async def stop_app(ctx: ToolContext[StudioDeps], payload: AppName) -> RunningApp:
    """Stop an App this window started."""
    deps = ctx.dependencies
    port = (await read_state(deps.root)).ports.get(payload.app_name)
    where = None if port is None else address(payload.app_name, deps.proxy_port)
    if not await deps.processes.stop(payload.app_name):
        return _refusal(
            payload.app_name,
            "hub.not_running",
            f"{payload.app_name!r} is not running here",
            category=ErrorCategory.CALLER,
            url=where,
        )
    return RunningApp(app_name=payload.app_name, url=where, state="installed")


RUNTIME_TOOLS: Sequence[Tool[StudioDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="start_app",
            description="Open an installed App's Web channel",
            input_model=StartRequest,
            output_model=RunningApp,
            read_only=False,
            channels=frozenset({Channel.WEB}),
        ),
        handler=start_app,
    ),
    Tool(
        definition=ToolDefinition(
            name="stop_app",
            description="Stop an App this Hub started",
            input_model=AppName,
            output_model=RunningApp,
            read_only=False,
            channels=frozenset({Channel.WEB}),
        ),
        handler=stop_app,
    ),
]
