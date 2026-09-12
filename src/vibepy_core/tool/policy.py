"""Authorization before input: from the declaration, the principal and the channel."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from vibepy_core.channel import Channel
from vibepy_core.errors import ToolForbiddenError
from vibepy_core.principal import Principal
from vibepy_core.tool.model import ToolDefinition


@dataclass(frozen=True, kw_only=True)
class AuthorizationRequest:
    """One call as a policy sees it: the Tool, who is calling, and through where."""

    definition: ToolDefinition[BaseModel, BaseModel]
    principal: Principal
    channel: Channel


class ToolPolicy(Protocol):
    """Refuses a call by raising `ToolForbiddenError`; returns to allow it."""

    def authorize(self, request: AuthorizationRequest, /) -> None:
        """Raise `ToolForbiddenError` to refuse `request`."""
        ...


class _DefaultPolicy:
    """What every declaration says: exposed on this channel, and the roles it requires."""

    def authorize(self, request: AuthorizationRequest, /) -> None:
        """Refuse a Tool not exposed on this channel, or one whose roles are missing."""
        definition = request.definition
        if request.channel not in definition.channels:
            raise ToolForbiddenError(
                definition.name,
                principal=request.principal.id,
                channel=request.channel.value,
                reason="not_exposed",
            )
        if definition.required_roles and not (definition.required_roles & request.principal.roles):
            raise ToolForbiddenError(
                definition.name,
                principal=request.principal.id,
                channel=request.channel.value,
                reason="role_required",
            )


default_policy: ToolPolicy = _DefaultPolicy()
"""The framework's policy. It always runs, and an App's policy runs after it."""
