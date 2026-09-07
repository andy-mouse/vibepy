"""The App layer's contract: one definition, independently isolated runtimes."""

import pytest
from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.errors import ToolNotFoundError
from vibepy.page import Page, PageContext, PageDefinition
from vibepy.tool import Tool, ToolContext, ToolDefinition


class Counter:
    """The app's application-scoped resource."""

    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> int:
        self.value += 1
        return self.value


class EmptyInput(BaseModel):
    pass


class Count(BaseModel):
    value: int


class Identity(BaseModel):
    app_id: str
    dependency_id: int


async def increment(ctx: ToolContext[Counter], _payload: EmptyInput) -> Count:
    return Count(value=ctx.dependencies.increment())


async def read(ctx: ToolContext[Counter], _payload: EmptyInput) -> Count:
    return Count(value=ctx.dependencies.value)


async def identify(ctx: ToolContext[Counter], _payload: EmptyInput) -> Identity:
    return Identity(app_id=ctx.app_id, dependency_id=id(ctx.dependencies))


INCREMENT = Tool(
    definition=ToolDefinition(
        name="increment",
        description="Add one to the counter",
        input_model=EmptyInput,
        output_model=Count,
    ),
    handler=increment,
)

READ = Tool(
    definition=ToolDefinition(
        name="read",
        description="Report the counter",
        input_model=EmptyInput,
        output_model=Count,
    ),
    handler=read,
)

IDENTIFY = Tool(
    definition=ToolDefinition(
        name="identify",
        description="Report the invocation's app id and dependency identity",
        input_model=EmptyInput,
        output_model=Identity,
    ),
    handler=identify,
)


async def counter_page(ctx: PageContext) -> None:
    await ctx.tools.invoke("increment", {})


def build_definition() -> AppDefinition[Counter]:
    return AppDefinition(
        app_id="counter-app",
        name="Counter",
        version="0.1.0",
        create_dependencies=Counter,
        tools=[INCREMENT, READ, IDENTIFY],
        pages=[
            Page(
                definition=PageDefinition(name="counter", route="/counter", title="Counter"),
                handler=counter_page,
            )
        ],
    )


async def test_calls_through_one_runtime_share_app_scoped_state() -> None:
    app = AppRuntime(build_definition())

    await app.tool_runtime.invoke("increment", {})
    await app.tool_runtime.invoke("increment", {})

    assert await app.tool_runtime.invoke("read", {}) == Count(value=2)


async def test_a_second_runtime_is_isolated_by_default() -> None:
    definition = build_definition()
    first = AppRuntime(definition)
    second = AppRuntime(definition)

    await first.tool_runtime.invoke("increment", {})

    assert await second.tool_runtime.invoke("read", {}) == Count(value=0)


async def test_every_invocation_receives_the_same_dependency_instance() -> None:
    app = AppRuntime(build_definition())

    first = await app.tool_runtime.invoke("identify", {})
    second = await app.tool_runtime.invoke("identify", {})

    assert isinstance(first, Identity)
    assert isinstance(second, Identity)
    assert first.dependency_id == second.dependency_id
    assert first.app_id == "counter-app"


async def test_a_declared_page_reaches_a_tool_through_the_runtime() -> None:
    app = AppRuntime(build_definition())

    await app.page_runtime.render("counter")

    assert await app.tool_runtime.invoke("read", {}) == Count(value=1)


def test_declared_tools_are_enumerable_for_channel_discovery() -> None:
    app = AppRuntime(build_definition())

    names = [definition.name for definition in app.tool_registry.definitions()]

    assert names == ["increment", "read", "identify"]


def test_declared_pages_are_enumerable_for_route_projection() -> None:
    app = AppRuntime(build_definition())

    routes = [definition.route for definition in app.page_registry.definitions()]

    assert routes == ["/counter"]


def test_the_definition_stays_reachable_from_the_runtime() -> None:
    definition = build_definition()

    app = AppRuntime(definition)

    assert app.definition is definition


async def test_an_unknown_tool_name_still_raises_through_the_app_runtime() -> None:
    app = AppRuntime(build_definition())

    with pytest.raises(ToolNotFoundError) as raised:
        await app.tool_runtime.invoke("nope", {})

    assert raised.value.tool_name == "nope"
