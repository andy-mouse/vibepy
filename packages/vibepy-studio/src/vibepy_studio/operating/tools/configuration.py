"""Holding the values one App runs with."""

from collections.abc import Sequence

from vibepy_core.channel import Channel
from vibepy_core.errors import ErrorCategory, ErrorInfo
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.operating.internals import (
    OperatingState,
    StudioDeps,
    held_secrets,
    secret_fields,
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

    The operating role does not validate them: the App's own window validates configuration
    as it opens and raises `config.invalid`. What it does do is keep a secret's
    value out of every answer it gives, so a value written once is not read back
    out through a channel.

    A value's place holds only values. A held secret is named beside them, so
    the answer this gives is safe to send back as a request: omitting a secret
    keeps it, and nothing this returns can overwrite one.
    """
    deps = ctx.dependencies
    facts = await deps.root.installed_facts(payload.app_name)
    if facts is None:
        return HeldConfig(
            app_name=payload.app_name,
            values={},
            secret_fields=[],
            secrets_set=[],
            diagnostic=ErrorInfo(
                code="operating.not_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts)

    def hold(state: OperatingState) -> OperatingState:
        return state.model_copy(
            update={
                "config": {
                    **state.config,
                    payload.app_name: {**state.config.get(payload.app_name, {}), **payload.values},
                }
            }
        )

    changed = await deps.root.update_state(hold)
    kept = changed.config[payload.app_name]
    return HeldConfig(
        app_name=payload.app_name,
        values=without_secrets(kept, secrets),
        secret_fields=list(secrets),
        secrets_set=list(held_secrets(kept, secrets)),
    )


async def describe_config(ctx: ToolContext[StudioDeps], payload: AppName) -> ConfigDescription:
    """Return what one App declares it needs, and what the operating role holds for it so far."""
    deps = ctx.dependencies
    facts = await deps.root.installed_facts(payload.app_name)
    if facts is None:
        return ConfigDescription(
            app_name=payload.app_name,
            diagnostic=ErrorInfo(
                code="operating.not_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts)
    held = (await deps.root.state()).config.get(payload.app_name, {})
    return ConfigDescription(
        app_name=payload.app_name,
        fields=list(facts.described.description.config_fields),
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
            read_only=False,
            channels=frozenset({Channel.WEB}),
        ),
        handler=configure_app,
    ),
    Tool(
        definition=ToolDefinition(
            name="describe_config",
            description="What an App declares it needs, and what is held for it",
            input_model=AppName,
            output_model=ConfigDescription,
            read_only=True,
            channels=frozenset({Channel.WEB}),
        ),
        handler=describe_config,
    ),
]
