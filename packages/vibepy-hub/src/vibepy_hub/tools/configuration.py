"""Holding the values one App runs with."""

from collections.abc import Sequence

from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_hub.internals import (
    HubDeps,
    HubState,
    installed_facts,
    masked,
    secret_fields,
    update_state,
)
from vibepy_hub.models import ConfigureRequest, Diagnostic, HeldConfig


async def configure_app(ctx: ToolContext[HubDeps], payload: ConfigureRequest) -> HeldConfig:
    """Hold the values one App runs with, its secrets included.

    The Hub does not validate them: the App's own window validates configuration
    as it opens and raises `config.invalid`. What it does do is keep a secret's
    value out of every answer it gives, so a value written once is not read back
    out through a channel.
    """
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return HeldConfig(
            app_name=payload.app_name,
            values={},
            secret_fields=[],
            diagnostic=Diagnostic(
                code="hub.not_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts.config_schema)

    def hold(state: HubState) -> HubState:
        return HubState(
            sources=state.sources,
            config={
                **state.config,
                payload.app_name: {**state.config.get(payload.app_name, {}), **payload.values},
            },
        )

    changed = await update_state(deps, hold)
    kept = changed.config[payload.app_name]
    return HeldConfig(
        app_name=payload.app_name,
        values=masked(kept, secrets),
        secret_fields=list(secrets),
    )


CONFIGURATION_TOOLS: Sequence[Tool[HubDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="configure_app",
            description="Hold the values an App runs with",
            input_model=ConfigureRequest,
            output_model=HeldConfig,
        ),
        handler=configure_app,
    ),
]
