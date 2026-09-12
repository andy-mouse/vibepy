"""The two headline invariants, where a linter cannot reach.

No MCP type reaches the core Tool model and no Web type reaches the core Page
model. The static half is `TID251` in `pyproject.toml`, which reads every core
module and exempts the two channel components; a rule a tool enforces is not
re-implemented as a test here.

What a static rule cannot see is an SDK reached through another import rather
than named in the file. That is behaviour, and it is what this checks.
`test_app_isolation.py` uses the same technique for the same reason.

The third invariant is the Tool's own: a Tool does not branch on the channel it
is reached through. What varies is where it is exposed, which the declaration
says and the runtime enforces, and that is checked here through both windows.
"""

import json
import subprocess
import sys

import pytest
from pydantic import BaseModel

from lifecycle import no_dependencies
from vibepy_core import (
    AppDefinition,
    Channel,
    NoConfig,
    Principal,
    ToolForbiddenError,
    tool_runtime_for,
)
from vibepy_core.tool import Tool, ToolContext, ToolDefinition

CHANNEL_SDKS = ("mcp", "nicegui")


class EmptyInput(BaseModel):
    pass


class Count(BaseModel):
    n: int


@pytest.mark.integration
def test_importing_the_core_loads_no_channel_sdk() -> None:
    probe = (
        "import json, sys; import vibepy_core; "
        "sys.stdout.write(json.dumps(sorted("
        "{module.split('.')[0] for module in sys.modules} "
        f"& set({list(CHANNEL_SDKS)!r}))))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout) == []


async def test_exposure_varies_by_channel_while_the_tool_does_not() -> None:
    calls: list[Channel] = []

    async def count(ctx: ToolContext[None], _payload: EmptyInput) -> Count:
        calls.append(ctx.channel)
        return Count(n=len(calls))

    agent_only = Tool(
        definition=ToolDefinition(
            name="count",
            description="Count",
            input_model=EmptyInput,
            output_model=Count,
            read_only=False,
            channels=frozenset({Channel.AGENT}),
        ),
        handler=count,
    )
    definition = AppDefinition(
        app_id="neutral",
        name="Neutral",
        version="0",
        config=NoConfig,
        tools=[agent_only],
        pages=[],
    )

    async with tool_runtime_for(
        definition, no_dependencies, config={}, channel=Channel.AGENT
    ) as agent:
        assert (await agent.invoke("count", {}, principal=Principal(id="a"))).model_dump() == {
            "n": 1
        }
    async with tool_runtime_for(definition, no_dependencies, config={}, channel=Channel.WEB) as web:
        with pytest.raises(ToolForbiddenError) as refused:
            await web.invoke("count", {}, principal=Principal(id="a"))

    assert refused.value.reason == "not_exposed"
    assert calls == [Channel.AGENT]
