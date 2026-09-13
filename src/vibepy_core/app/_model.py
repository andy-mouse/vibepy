"""Declaration of an App. A value: it holds no resource and no runtime state.

A declaration validates itself as it is constructed, so an invalid one cannot
exist and nothing downstream checks again. The rules that need the whole App --
uniqueness across Tools and Pages, a Page's reference to a Tool -- run here,
because this is the one object that holds every Tool and Page. ADR-037.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from vibepy_core.app.config import AppConfig, NoConfig
from vibepy_core.channel import Channel
from vibepy_core.errors import (
    AppDefinitionInvalidError,
    PageNameConflictError,
    PageRouteConflictError,
    PageRouteInvalidError,
    PageToolUnresolvedError,
    ToolNameConflictError,
    VibepyError,
)
from vibepy_core.page._model import Page
from vibepy_core.tool._policy import ToolPolicy
from vibepy_core.tool._runtime import Tool

__all__ = ["AppConfig", "AppDefinition", "NoConfig"]


@dataclass(frozen=True, kw_only=True)
class AppDefinition[DepsT, ConfigT: AppConfig]:
    """Everything a channel needs to know about an App without running it.

    ``DepsT`` is the app's own type for its application-scoped resource. The
    definition declares that its Tools require one of that type; it does not
    declare where one comes from. An entrypoint supplies that at composition
    time, and the type checker rejects a mismatch at that one site.

    An App whose Tools need no resource declares ``AppDefinition[None, ...]``.

    ``config`` is the opposite kind of type: an `AppConfig` subclass the
    framework instantiates and projects. It is what this App requires of its
    host, and it is readable without acquiring anything.

    ``policy`` is the App's own authorization. It runs after the framework's, so
    it may refuse further and never admit what a declaration refuses.

    Constructing one runs every cross-declaration rule and raises
    `AppDefinitionInvalidError` carrying each violation found, in declaration
    order. A definition that exists therefore conforms.
    """

    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
    policy: ToolPolicy | None = None

    def __post_init__(self) -> None:
        """Hold the declaration to its rules; collect every violation, raise once.

        Raises:
            AppDefinitionInvalidError: at least one rule is broken; `errors` holds all.
        """
        found = [*_tool_violations(self.tools), *_page_violations(self.tools, self.pages)]
        if found:
            raise AppDefinitionInvalidError(self.app_id, found)


def _tool_violations[DepsT](tools: Sequence[Tool[DepsT]], /) -> list[VibepyError]:
    """Two Tools may not share a name: a channel would publish two and answer both with one."""
    seen: set[str] = set()
    found: list[VibepyError] = []
    for tool in tools:
        name = tool.definition.name
        if name in seen:
            found.append(ToolNameConflictError(name))
        seen.add(name)
    return found


def _page_violations[DepsT](
    tools: Sequence[Tool[DepsT]], pages: Sequence[Page], /
) -> list[VibepyError]:
    """Names and routes unique, routes rooted, and every declared Tool present and on the Web."""
    web_tools = {t.definition.name for t in tools if Channel.WEB in t.definition.channels}
    all_tools = {t.definition.name for t in tools}
    names: dict[str, str] = {}
    routes: dict[str, str] = {}
    found: list[VibepyError] = []
    for page in pages:
        declared = page.definition
        owner_route = names.get(declared.name)
        if owner_route is not None:
            found.append(PageNameConflictError(declared.name, owner_route, declared.route))
        else:
            names[declared.name] = declared.route
        if not declared.route.startswith("/"):
            found.append(PageRouteInvalidError(declared.name, declared.route))
        else:
            owner_name = routes.get(declared.route)
            if owner_name is not None:
                found.append(PageRouteConflictError(declared.route, owner_name, declared.name))
            else:
                routes[declared.route] = declared.name
        for tool_name in sorted(declared.tools):
            if tool_name not in all_tools:
                found.append(PageToolUnresolvedError(declared.name, tool_name, reason="missing"))
            elif tool_name not in web_tools:
                found.append(
                    PageToolUnresolvedError(declared.name, tool_name, reason="not_exposed")
                )
    return found
