"""Declaration of an App. A value: it holds no resource and no runtime state."""

from collections.abc import Sequence
from dataclasses import dataclass

from vibepy_core.app.config import AppConfig, NoConfig
from vibepy_core.page.model import Page
from vibepy_core.tool.policy import ToolPolicy
from vibepy_core.tool.runtime import Tool

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
    """

    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
    policy: ToolPolicy | None = None
