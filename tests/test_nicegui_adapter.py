import ast
from pathlib import Path

# NiceGUI types ``user_simulation``'s unused ``root`` parameter as a bare Callable, so
# pyright cannot fully resolve the name. The context manager it returns is typed.
from nicegui import app, ui
from nicegui.testing import user_simulation  # pyright: ignore[reportUnknownVariableType]
from starlette.routing import Route

from vibepy.adapters.nicegui import register_pages
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
