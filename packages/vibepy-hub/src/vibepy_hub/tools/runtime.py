"""Opening and closing an installed App's Web channel."""

import logging
from collections.abc import Sequence

from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import (
    HubDeps,
    StartFailed,
    environment,
    installed_facts,
    interpreter,
    read_state,
)
from vibepy_hub.models import AppName, Diagnostic, RunningApp, StartRequest

logger = logging.getLogger(__name__)


def _refusal(app_name: str, code: str, message: str, /, *, category: ErrorCategory) -> RunningApp:
    """An App that will not start or stop, and why."""
    return RunningApp(
        app_name=app_name,
        state="installed",
        diagnostic=Diagnostic(
            code=code, category=category, message=message, details={"app_name": app_name}
        ),
    )


def _category(reported: str, /) -> ErrorCategory:
    """The category a child named, or execution when it named one we do not know."""
    try:
        return ErrorCategory(reported)
    except ValueError:
        logger.debug("a child reported an unknown category: %s", reported)
        return ErrorCategory.EXECUTION


async def start_app(ctx: ToolContext[HubDeps], payload: StartRequest) -> RunningApp:
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
    if deps.processes.running(payload.app_name) is not None:
        return _refusal(
            payload.app_name,
            "hub.already_running",
            f"{payload.app_name!r} is already running",
            category=ErrorCategory.CALLER,
        )
    held = (await read_state(deps.root)).config.get(payload.app_name, {})
    try:
        port = await deps.processes.start(
            app_name=facts.declared_name,
            interpreter=interpreter(environment(deps.root, payload.app_name)),
            config={**held, **payload.secrets},
            known_as=payload.app_name,
        )
    except StartFailed as failure:
        reported = failure.reported
        if reported is None:
            return _refusal(
                payload.app_name,
                "hub.start_failed",
                str(failure),
                category=ErrorCategory.EXECUTION,
            )
        return RunningApp(
            app_name=payload.app_name,
            state="installed",
            diagnostic=Diagnostic(
                code=reported.code,
                category=_category(reported.category),
                message=reported.message,
                details={"app_name": payload.app_name, **reported.details},
            ),
        )
    return RunningApp(app_name=payload.app_name, url=f"http://127.0.0.1:{port}", state="running")


async def stop_app(ctx: ToolContext[HubDeps], payload: AppName) -> RunningApp:
    """Stop an App this window started."""
    if not await ctx.dependencies.processes.stop(payload.app_name):
        return _refusal(
            payload.app_name,
            "hub.not_running",
            f"{payload.app_name!r} is not running here",
            category=ErrorCategory.CALLER,
        )
    return RunningApp(app_name=payload.app_name, state="installed")


RUNTIME_TOOLS: Sequence[Tool[HubDeps]] = [
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
]
