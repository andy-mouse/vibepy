"""The Web channel adapter's contract.

Every test isolates NiceGUI's process-global route table, most by requesting
the ``user`` fixture — including the ones that never open a page. The two that
expect a render to fail drive ``user_simulation`` instead, which is what that
fixture is built on and which performs the same reset: the fixture also fails a
test on any ERROR log, and a render that raises logs one.
"""

import pytest
from nicegui import app, ui
from nicegui.testing import User, user_simulation  # pyright: ignore[reportUnknownVariableType]
from starlette.routing import Route

from tests.lifecycle import no_dependencies
from todo_app.entry import TODO_APP, TODO_CONFIG, todo_lifespan
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import AppDefinition, NoConfig, page_runtime_for
from vibepy_core.errors import (
    PageRouteConflictError,
    PageRouteInvalidError,
    ToolNotFoundError,
)
from vibepy_core.page import Page, PageContext, PageDefinition, PageHandler

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
                definition=PageDefinition(name="todos", route="/todos", title="Todos"),
                handler=handler,
            )
        ]
    )

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        register_pages(definition, pages)

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
                definition=PageDefinition(name="todos", route="/todos", title="Todos"),
                handler=handler,
            )
        ]
    )

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        register_pages(definition, pages)
        await user.open("/todos")

    assert len(seen) == 1
    assert callable(seen[0].tools.invoke)


async def noop_handler(ctx: PageContext) -> None:
    ui.label("Todos")


def page(name: str, route: str) -> Page:
    return Page(
        definition=PageDefinition(name=name, route=route, title=name),
        handler=noop_handler,
    )


async def test_a_route_that_is_not_a_path_is_rejected(user: User) -> None:
    definition = web_definition([page("todos", "todos")])

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        with pytest.raises(PageRouteInvalidError) as error:
            register_pages(definition, pages)

    assert error.value.page_name == "todos"
    assert error.value.route == "todos"


async def test_two_pages_may_not_claim_one_route(user: User) -> None:
    definition = web_definition([page("todos", "/todos"), page("archive", "/todos")])

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        with pytest.raises(PageRouteConflictError) as error:
            register_pages(definition, pages)

    assert error.value.route == "/todos"
    assert {error.value.page_name, error.value.conflicting_page_name} == {"todos", "archive"}


async def test_a_rejected_registry_registers_nothing(user: User) -> None:
    definition = web_definition([page("todos", "/todos"), page("archive", "archive")])

    async with page_runtime_for(definition, no_dependencies, config={}) as pages:
        with pytest.raises(PageRouteInvalidError):
            register_pages(definition, pages)

    assert "/todos" not in registered_paths()


async def test_page_interaction_invokes_a_tool(user: User) -> None:
    async with page_runtime_for(TODO_APP, todo_lifespan, config=TODO_CONFIG) as pages:
        register_pages(TODO_APP, pages)
        await user.open("/todos")
        user.find("title").type("write the spec")
        user.find("Add").click()
        await user.should_see("todo: write the spec")


class HandlersOwnError(Exception):
    """An exception an App's own Page handler raises."""


def boom_definition(handler: PageHandler) -> AppDefinition[None, NoConfig]:
    return web_definition(
        [
            Page(
                definition=PageDefinition(name="boom", route="/boom", title="Boom"),
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
            register_pages(definition, pages)

            with pytest.raises(ToolNotFoundError):
                await user.open("/boom")


async def test_an_app_exception_raised_in_a_render_is_not_translated() -> None:
    async def handler(_ctx: PageContext) -> None:
        raise HandlersOwnError("the app's own failure")

    definition = boom_definition(handler)

    async with user_simulation() as user:
        async with page_runtime_for(definition, no_dependencies, config={}) as pages:
            register_pages(definition, pages)

            with pytest.raises(HandlersOwnError):
                await user.open("/boom")
