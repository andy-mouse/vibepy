"""The Web channel adapter's contract.

Every test requests NiceGUI's ``user`` fixture, including the ones that never
open a page: the fixture is what resets NiceGUI's process-global route table
around each test.
"""

import ast
from pathlib import Path

import pytest
from nicegui import app, ui
from nicegui.testing import User
from starlette.routing import Route

from tests.lifecycle import no_dependencies
from tests.todo_fixture import TODO_PLUGIN, todo_lifespan
from vibepy.adapters.nicegui import register_pages
from vibepy.errors import PageRouteConflictError, PageRouteInvalidError
from vibepy.page import Page, PageContext, PageDefinition
from vibepy.plugin import PluginDefinition, page_runtime_for

PLUGIN_ID = "test-app"


def web_definition(pages: list[Page]) -> PluginDefinition[None]:
    """One Plugin with no Tools and no application-scoped resource: routes only."""
    return PluginDefinition(
        plugin_id=PLUGIN_ID,
        name="Test",
        version="0.0.0",
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

    async with page_runtime_for(definition, no_dependencies) as pages:
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

    async with page_runtime_for(definition, no_dependencies) as pages:
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

    async with page_runtime_for(definition, no_dependencies) as pages:
        with pytest.raises(PageRouteInvalidError) as error:
            register_pages(definition, pages)

    assert error.value.page_name == "todos"
    assert error.value.route == "todos"


async def test_two_pages_may_not_claim_one_route(user: User) -> None:
    definition = web_definition([page("todos", "/todos"), page("archive", "/todos")])

    async with page_runtime_for(definition, no_dependencies) as pages:
        with pytest.raises(PageRouteConflictError) as error:
            register_pages(definition, pages)

    assert error.value.route == "/todos"
    assert {error.value.page_name, error.value.conflicting_page_name} == {"todos", "archive"}


async def test_a_rejected_registry_registers_nothing(user: User) -> None:
    definition = web_definition([page("todos", "/todos"), page("archive", "archive")])

    async with page_runtime_for(definition, no_dependencies) as pages:
        with pytest.raises(PageRouteInvalidError):
            register_pages(definition, pages)

    assert "/todos" not in registered_paths()


async def test_page_interaction_invokes_a_tool(user: User) -> None:
    async with page_runtime_for(TODO_PLUGIN, todo_lifespan) as pages:
        register_pages(TODO_PLUGIN, pages)
        await user.open("/todos")
        user.find("title").type("write the spec")
        user.find("Add").click()
        await user.should_see("todo: write the spec")


def _imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_the_core_packages_do_not_import_nicegui() -> None:
    package = Path(__file__).resolve().parent.parent / "src" / "vibepy"
    modules = (
        sorted((package / "tool").glob("*.py"))
        + sorted((package / "page").glob("*.py"))
        + sorted((package / "plugin").glob("*.py"))
    )
    assert modules != []

    offenders = [
        module.name
        for module in modules
        for name in _imported_module_names(module.read_text(encoding="utf-8"))
        if name == "nicegui" or name.startswith("nicegui.")
    ]

    assert offenders == []
