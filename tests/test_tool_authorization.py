"""The refusal contract: ToolRuntime authorizes before it validates, from the declaration."""

import pytest
from pydantic import BaseModel

from vibepy_core import Channel, Principal
from vibepy_core.errors import ToolForbiddenError
from vibepy_core.tool import (
    AuthorizationRequest,
    Tool,
    ToolContext,
    ToolDefinition,
    ToolPolicy,
    ToolRegistry,
    ToolRuntime,
)


class Amount(BaseModel):
    amount: int


class Receipt(BaseModel):
    amount: int
    by: str


class Recorder:
    def __init__(self) -> None:
        self.calls: list[ToolContext[object]] = []


async def approve(ctx: ToolContext[Recorder], payload: Amount) -> Receipt:
    ctx.dependencies.calls.append(ctx)
    return Receipt(amount=payload.amount, by=ctx.principal.id)


def approve_tool(
    *, channels: frozenset[Channel] = frozenset(Channel), roles: frozenset[str] = frozenset()
) -> Tool[Recorder]:
    return Tool(
        definition=ToolDefinition(
            name="approve",
            description="Approve an amount",
            input_model=Amount,
            output_model=Receipt,
            read_only=False,
            channels=channels,
            required_roles=roles,
        ),
        handler=approve,
    )


def runtime(
    tool: Tool[Recorder], *, channel: Channel, policy: ToolPolicy | None = None
) -> tuple[ToolRuntime[Recorder], Recorder]:
    registry: ToolRegistry[Recorder] = ToolRegistry()
    registry.register(tool)
    recorder = Recorder()
    return (
        ToolRuntime(
            app_id="expense",
            registry=registry,
            dependencies=recorder,
            channel=channel,
            policy=policy,
        ),
        recorder,
    )


ALICE = Principal(id="alice")
MANAGER = Principal(id="bob", roles=frozenset({"manager"}))


async def test_a_tool_not_exposed_on_the_channel_is_refused_before_the_handler() -> None:
    run, recorder = runtime(approve_tool(channels=frozenset({Channel.WEB})), channel=Channel.AGENT)

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=ALICE)

    assert refused.value.reason == "not_exposed"
    assert recorder.calls == []


async def test_a_role_gated_tool_refuses_a_principal_without_the_role() -> None:
    run, recorder = runtime(approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT)

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=ALICE)

    assert refused.value.reason == "role_required"
    assert refused.value.details()["principal"] == "alice"
    assert recorder.calls == []


async def test_a_role_gated_tool_runs_for_a_principal_with_the_role() -> None:
    run, recorder = runtime(approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT)

    result = await run.invoke("approve", {"amount": 1}, principal=MANAGER)

    assert result == Receipt(amount=1, by="bob")
    assert len(recorder.calls) == 1


async def test_a_tool_requiring_no_role_runs_for_a_principal_with_none() -> None:
    run, _ = runtime(approve_tool(), channel=Channel.WEB)

    assert await run.invoke("approve", {"amount": 2}, principal=ALICE) == Receipt(
        amount=2, by="alice"
    )


async def test_refusal_comes_before_input_validation() -> None:
    run, recorder = runtime(approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT)

    with pytest.raises(ToolForbiddenError):
        await run.invoke("approve", {"amount": "not a number"}, principal=ALICE)
    assert recorder.calls == []


class RefuseEveryone:
    def authorize(self, request: AuthorizationRequest, /) -> None:
        raise ToolForbiddenError(
            request.definition.name,
            principal=request.principal.id,
            channel=request.channel.value,
            reason="closed_for_audit",
        )


async def test_an_app_policy_may_refuse_with_its_own_reason() -> None:
    run, recorder = runtime(approve_tool(), channel=Channel.AGENT, policy=RefuseEveryone())

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=MANAGER)

    assert refused.value.reason == "closed_for_audit"
    assert recorder.calls == []


class AdmitEveryone:
    def authorize(self, request: AuthorizationRequest, /) -> None:
        return None


async def test_an_app_policy_cannot_admit_what_the_declaration_refuses() -> None:
    run, recorder = runtime(
        approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT, policy=AdmitEveryone()
    )

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=ALICE)

    assert refused.value.reason == "role_required"
    assert recorder.calls == []


async def test_the_context_carries_the_principal_and_the_channel() -> None:
    run, recorder = runtime(approve_tool(), channel=Channel.WEB)

    await run.invoke("approve", {"amount": 1}, principal=ALICE)

    ctx = recorder.calls[0]
    assert ctx.principal == ALICE
    assert ctx.channel is Channel.WEB
