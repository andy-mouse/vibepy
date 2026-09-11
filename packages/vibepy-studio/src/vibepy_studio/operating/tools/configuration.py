"""Holding the values one App runs with."""

from collections.abc import Sequence

from vibepy_core.errors import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.internals import StudioDeps
from vibepy_studio.models import Diagnostic
from vibepy_studio.operating.internals import (
    HubState,
    config_fields,
    held_secrets,
    installed_facts,
    read_state,
    secret_fields,
    update_state,
    without_secrets,
)
from vibepy_studio.operating.models import (
    AppName,
    ConfigDescription,
    ConfigureRequest,
    HeldConfig,
)


async def configure_app(ctx: ToolContext[StudioDeps], payload: ConfigureRequest) -> HeldConfig:
    """Hold the values one App runs with, its secrets included.

    The Hub does not validate them: the App's own window validates configuration
    as it opens and raises `config.invalid`. What it does do is keep a secret's
    value out of every answer it gives, so a value written once is not read back
    out through a channel.

    A value's place holds only values. A held secret is named beside them, so
    the answer this gives is safe to send back as a request: omitting a secret
    keeps it, and nothing this returns can overwrite one.
    """
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return HeldConfig(
            app_name=payload.app_name,
            values={},
            secret_fields=[],
            secrets_set=[],
            diagnostic=Diagnostic(
                code="hub.not_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts.config_schema)

    def hold(state: HubState) -> HubState:
        return state.model_copy(
            update={
                "config": {
                    **state.config,
                    payload.app_name: {**state.config.get(payload.app_name, {}), **payload.values},
                }
            }
        )

    changed = await update_state(deps, hold)
    kept = changed.config[payload.app_name]
    return HeldConfig(
        app_name=payload.app_name,
        values=without_secrets(kept, secrets),
        secret_fields=list(secrets),
        secrets_set=list(held_secrets(kept, secrets)),
    )


async def describe_config(ctx: ToolContext[StudioDeps], payload: AppName) -> ConfigDescription:
    """Return what one App declares it needs, and what the Hub holds for it so far."""
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return ConfigDescription(
            app_name=payload.app_name,
            diagnostic=Diagnostic(
                code="hub.not_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts.config_schema)
    held = (await read_state(deps.root)).config.get(payload.app_name, {})
    return ConfigDescription(
        app_name=payload.app_name,
        fields=list(config_fields(facts.config_schema)),
        values=without_secrets(held, secrets),
        secrets_set=list(held_secrets(held, secrets)),
    )


CONFIGURATION_TOOLS: Sequence[Tool[StudioDeps]] = [
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
            name="describe_config",
            description="What an App declares it needs, and what is held for it",
            input_model=AppName,
            output_model=ConfigDescription,
        ),
        handler=describe_config,
    ),
]
