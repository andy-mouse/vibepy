import ast
from pathlib import Path

import pytest

# NiceGUI types ``user_simulation``'s unused ``root`` parameter as a bare Callable, so
# pyright cannot fully resolve the name. The context manager it returns is typed.
from nicegui import app, ui
from nicegui.testing import user_simulation  # pyright: ignore[reportUnknownVariableType]
from starlette.routing import Route

from tests.todo_fixture import build_todo_app
from vibepy.adapters.nicegui import register_pages
from vibepy.errors import PageRouteConflictError, PageRouteInvalidError
from vibepy.page import Page, PageContext, PageDefinition, PageRegistry, PageRuntime
from vibepy.tool import ToolRegistry, ToolRuntime

APP_ID = "test-app"


def build_runtime(registry: PageRegistry) -> PageRuntime:
    tool_registry = ToolRegistry()
    return PageRuntime(
        registry=registry,
        tool_runtime=ToolRuntime(app_id=APP_ID, registry=tool_registry),
    )


def registered_paths() -> list[str]:
    return [route.path for route in app.routes if isinstance(route, Route)]


async def test_a_page_definition_becomes_a_web_route() -> None:
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        ui.label("Todos")

    registry.register(
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=handler,
        )
    )

    async with user_simulation() as user:
        register_pages(registry=registry, runtime=build_runtime(registry))

        assert "/todos" in registered_paths()
        await user.open("/todos")
        await user.should_see("Todos")


async def test_the_handler_receives_a_page_context() -> None:
    registry = PageRegistry()
    seen: list[PageContext] = []

    async def handler(ctx: PageContext) -> None:
        seen.append(ctx)
        ui.label("Todos")

    registry.register(
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=handler,
        )
    )

    async with user_simulation() as user:
        register_pages(registry=registry, runtime=build_runtime(registry))
        await user.open("/todos")

    assert len(seen) == 1
    assert callable(seen[0].tools.call)


async def noop_handler(ctx: PageContext) -> None:
    ui.label("Todos")


def page(name: str, route: str) -> Page:
    return Page(
        definition=PageDefinition(name=name, route=route, title=name),
        handler=noop_handler,
    )


async def test_a_route_that_is_not_a_path_is_rejected() -> None:
    registry = PageRegistry()
    registry.register(page("todos", "todos"))

    async with user_simulation():
        with pytest.raises(PageRouteInvalidError) as error:
            register_pages(registry=registry, runtime=build_runtime(registry))

    assert error.value.page_name == "todos"
    assert error.value.route == "todos"


async def test_two_pages_may_not_claim_one_route() -> None:
    registry = PageRegistry()
    registry.register(page("todos", "/todos"))
    registry.register(page("archive", "/todos"))

    async with user_simulation():
        with pytest.raises(PageRouteConflictError) as error:
            register_pages(registry=registry, runtime=build_runtime(registry))

    assert error.value.route == "/todos"
    assert {error.value.page_name, error.value.conflicting_page_name} == {"todos", "archive"}


async def test_a_rejected_registry_registers_nothing() -> None:
    registry = PageRegistry()
    registry.register(page("todos", "/todos"))
    registry.register(page("archive", "archive"))

    async with user_simulation():
        with pytest.raises(PageRouteInvalidError):
            register_pages(registry=registry, runtime=build_runtime(registry))

        assert "/todos" not in registered_paths()


async def test_page_interaction_invokes_a_tool() -> None:
    app_under_test = build_todo_app()

    async with user_simulation() as user:
        register_pages(
            registry=app_under_test.page_registry,
            runtime=app_under_test.page_runtime,
        )
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


def test_the_core_tool_and_page_packages_do_not_import_nicegui() -> None:
    package = Path(__file__).resolve().parent.parent / "src" / "vibepy"
    modules = sorted((package / "tool").glob("*.py")) + sorted((package / "page").glob("*.py"))
    assert modules != []

    offenders = [
        module.name
        for module in modules
        for name in _imported_module_names(module.read_text(encoding="utf-8"))
        if name == "nicegui" or name.startswith("nicegui.")
    ]

    assert offenders == []
