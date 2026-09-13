"""What an AppDefinition may be: the rules a declaration is held to as it is constructed.

An invalid declaration cannot exist. Every violation is collected and raised once,
so an author learns them all from one construction, and nothing downstream checks
again. `docs/architecture/app-model.md`; ADR-037.
"""

import subprocess
import sys

import pytest
from pydantic import BaseModel

from lifecycle import no_dependencies
from vibepy_core import Channel
from vibepy_core.app import AppDefinition, AppEntrypoint, NoConfig
from vibepy_core.errors import (
    AppDefinitionInvalidError,
    PageNameConflictError,
    PageRouteConflictError,
    PageRouteInvalidError,
    PageToolUnresolvedError,
    ToolNameConflictError,
)
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


class Empty(BaseModel):
    pass


async def noop_tool(_ctx: ToolContext[None], _payload: Empty) -> Empty:
    return Empty()


async def noop_page(_ctx: PageContext) -> None:
    return None


def tool(name: str, *, channels: frozenset[Channel] = frozenset(Channel)) -> Tool[None]:
    return Tool(
        definition=ToolDefinition(
            name=name,
            description=name,
            input_model=Empty,
            output_model=Empty,
            read_only=True,
            channels=channels,
        ),
        handler=noop_tool,
    )


def page(name: str, route: str, tools: frozenset[str] = frozenset()) -> Page:
    return Page(
        definition=PageDefinition(name=name, route=route, title=name, tools=tools),
        handler=noop_page,
    )


def definition(tools: list[Tool[None]], pages: list[Page]) -> AppDefinition[None, NoConfig]:
    return AppDefinition(
        app_id="conformance",
        name="Conformance",
        version="0.0.0",
        config=NoConfig,
        tools=tools,
        pages=pages,
    )


def test_a_conforming_declaration_constructs_and_describes_the_same_twice() -> None:
    declared = definition([tool("read"), tool("write")], [page("home", "/", frozenset({"read"}))])

    first = AppEntrypoint(definition=declared, lifespan=no_dependencies).describe()
    second = AppEntrypoint(definition=declared, lifespan=no_dependencies).describe()

    assert first == second
    assert first.pages[0].tools == ["read"]


def test_every_violation_is_collected_and_raised_once() -> None:
    with pytest.raises(AppDefinitionInvalidError) as raised:
        definition(
            [tool("read"), tool("read"), tool("hidden", channels=frozenset({Channel.AGENT}))],
            [
                page("home", "/", frozenset({"read"})),
                page("home", "no-slash", frozenset({"absent", "hidden"})),
                page("list", "/", frozenset()),
            ],
        )

    error = raised.value
    assert error.app_id == "conformance"
    assert [type(member) for member in error.errors] == [
        ToolNameConflictError,
        PageNameConflictError,
        PageRouteInvalidError,
        PageToolUnresolvedError,
        PageToolUnresolvedError,
        PageRouteConflictError,
    ]
    conflict, name, route, absent, hidden, claimed = error.errors
    assert isinstance(conflict, ToolNameConflictError) and conflict.tool_name == "read"
    assert isinstance(name, PageNameConflictError) and name.page_name == "home"
    assert isinstance(route, PageRouteInvalidError) and route.route == "no-slash"
    assert isinstance(absent, PageToolUnresolvedError)
    assert (absent.tool_name, absent.reason) == ("absent", "missing")
    assert isinstance(hidden, PageToolUnresolvedError)
    assert (hidden.tool_name, hidden.reason) == ("hidden", "not_exposed")
    assert isinstance(claimed, PageRouteConflictError)
    assert claimed.route == "/" and {claimed.page_name, claimed.conflicting_page_name} == {
        "home",
        "list",
    }


def test_one_violation_is_raised_in_the_same_shape() -> None:
    with pytest.raises(AppDefinitionInvalidError) as raised:
        definition([tool("read")], [page("home", "home")])

    assert len(raised.value.errors) == 1
    assert isinstance(raised.value.errors[0], PageRouteInvalidError)


def test_a_page_may_invoke_a_tool_exposed_to_the_web_channel_only() -> None:
    declared = definition(
        [tool("read", channels=frozenset({Channel.WEB}))], [page("home", "/", frozenset({"read"}))]
    )

    assert declared.pages[0].definition.tools == frozenset({"read"})


def test_the_rules_import_no_channel_adapter() -> None:
    """The third acceptance criterion: conformance knows no channel implementation."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import vibepy_core.app, sys; "
            "sys.exit(any(n.startswith('vibepy_core.adapters') for n in sys.modules))",
        ],
        check=False,
    )
    assert result.returncode == 0
