"""The Web channel adapter's contract.

Every test isolates NiceGUI's process-global route table, most by requesting
the ``user`` fixture — including the ones that never open a page. The two that
expect a render to fail drive ``user_simulation`` instead, which is what that
fixture is built on and which performs the same reset: the fixture also fails a
test on any ERROR log, and a render that raises logs one.
"""

from pathlib import Path

import pytest
from nicegui import app, ui
from nicegui.testing import User, user_simulation  # pyright: ignore[reportUnknownVariableType]
from pydantic import BaseModel
from starlette.routing import Route

from lifecycle import no_dependencies
from todo_app.entry import TODO_APP, todo_lifespan
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import AppDefinition, NoConfig, page_runtime_for
from vibepy_core.errors import ToolNotFoundError
from vibepy_core.page import Page, PageContext, PageDefinition, PageHandler
from vibepy_core.principal import Principal
from vibepy_core.tool import Tool, ToolContext, ToolDefinition

APP_ID = "test-app"


def web_definition(pages: list[Page]) -> AppDefinition[None, NoConfig]:
    """One App with no Tools and no application-scoped resource: routes only."""
    return AppDefinition(
        app_id=APP_ID,
        name="Test",
        version="0.0.0",
        config=NoConfig,
        tools=[],
        pages=pages,
    )


def registered_paths() -> list[str]:
    return [route.path for route in app.routes if isinstance(route, Route)]


async def test_a_page_definition_becomes_a_web_route(user: User) -> None:
    async def handler(ctx: PageContext) -> None:
        ui.label("Todos")

    definition = web_definition(
        [
            Page(
                definition=PageDefinition(
                    name="todos", route="/todos", title="Todos", tools=frozenset()
                ),
                handler=handler,
            )
        ]
    )

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        register_pages(definition, pages, principal=Principal(id="operator"))

        assert "/todos" in registered_paths()
        await user.open("/todos")
        await user.should_see("Todos")


async def test_the_handler_receives_a_page_context(user: User) -> None:
    seen: list[PageContext] = []

    async def handler(ctx: PageContext) -> None:
        seen.append(ctx)
        ui.label("Todos")

    definition = web_definition(
        [
            Page(
                definition=PageDefinition(
                    name="todos", route="/todos", title="Todos", tools=frozenset()
                ),
                handler=handler,
            )
        ]
    )

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        register_pages(definition, pages, principal=Principal(id="operator"))
        await user.open("/todos")

    assert len(seen) == 1
    assert callable(seen[0].tools.invoke)


async def noop_handler(ctx: PageContext) -> None:
    ui.label("Todos")


def page(name: str, route: str, *, tools: frozenset[str] = frozenset()) -> Page:
    return Page(
        definition=PageDefinition(name=name, route=route, title=name, tools=tools),
        handler=noop_handler,
    )


async def test_page_interaction_invokes_a_tool(user: User, tmp_path: Path) -> None:
    config = {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}
    async with page_runtime_for(TODO_APP, todo_lifespan, config=config) as pages:
        register_pages(TODO_APP, pages, principal=Principal(id="operator"))
        await user.open("/todos")
        user.find("title").type("write the spec")
        user.find("Add").click()
        await user.should_see("todo: write the spec")


class EmptyInput(BaseModel):
    pass


async def test_the_hosts_principal_reaches_a_pages_tool_call(user: User) -> None:
    seen: list[Principal] = []

    async def who(ctx: ToolContext[None], _payload: EmptyInput) -> EmptyInput:
        seen.append(ctx.principal)
        return EmptyInput()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.invoke("who", {})

    definition = AppDefinition(
        app_id=APP_ID,
        name="Test",
        version="0.0.0",
        config=NoConfig,
        tools=[
            Tool(
                definition=ToolDefinition(
                    name="who",
                    description="Report the invoking principal",
                    input_model=EmptyInput,
                    output_model=EmptyInput,
                    read_only=True,
                ),
                handler=who,
            )
        ],
        pages=[
            Page(
                definition=PageDefinition(
                    name="home", route="/home", title="Home", tools=frozenset({"who"})
                ),
                handler=handler,
            )
        ],
    )
    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        register_pages(definition, pages, principal=Principal(id="host"))
        await user.open("/home")

    assert seen == [Principal(id="host")]


class HandlersOwnError(Exception):
    """An exception an App's own Page handler raises."""


def boom_definition(handler: PageHandler) -> AppDefinition[None, NoConfig]:
    return web_definition(
        [
            Page(
                definition=PageDefinition(
                    name="boom", route="/boom", title="Boom", tools=frozenset()
                ),
                handler=handler,
            )
        ]
    )


async def test_a_framework_error_raised_in_a_render_is_not_translated() -> None:
    """`errors.md`: the Web channel translates nothing.

    These two drive `user_simulation` rather than the `user` fixture: that
    fixture fails a test on any ERROR log and a render that raises logs one.
    `user_simulation` is the context manager the fixture is built on and is
    what `nicegui.testing` exports, so this is the library's own entry point.
    """

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.invoke("absent", {})

    definition = boom_definition(handler)

    async with user_simulation() as user:
        async with page_runtime_for(definition, no_dependencies, config={}) as pages:
            register_pages(definition, pages, principal=Principal(id="operator"))

            with pytest.raises(ToolNotFoundError):
                await user.open("/boom")


async def test_an_app_exception_raised_in_a_render_is_not_translated() -> None:
    async def handler(_ctx: PageContext) -> None:
        raise HandlersOwnError("the app's own failure")

    definition = boom_definition(handler)

    async with user_simulation() as user:
        async with page_runtime_for(definition, no_dependencies, config={}) as pages:
            register_pages(definition, pages, principal=Principal(id="operator"))

            with pytest.raises(HandlersOwnError):
                await user.open("/boom")
