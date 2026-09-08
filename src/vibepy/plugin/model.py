"""Declaration of a Plugin. A value: it holds no resource and no runtime state."""

from collections.abc import Sequence
from dataclasses import dataclass

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


@dataclass(frozen=True)
class PluginDefinition[DepsT]:
    """Everything a channel needs to know about a Plugin without running it.

    ``DepsT`` is the plugin's own type for its application-scoped resource. The
    definition declares that its Tools require one of that type; it does not
    declare where one comes from. An entrypoint supplies that at composition
    time, and the type checker rejects a mismatch at that one site. See
    `docs/decisions/ADR-022-a-declaration-holds-no-resource-factory.md`.

    A Plugin whose Tools need no resource declares ``PluginDefinition[None]``.
    """

    plugin_id: str
    name: str
    version: str
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
