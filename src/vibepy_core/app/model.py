"""Declaration of an App. A value: it holds no resource and no runtime state."""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from vibepy_core.page.model import Page
from vibepy_core.tool.runtime import Tool


class NoConfig(BaseModel):
    """The configuration of an App that requires nothing of its host.

    Declared explicitly rather than defaulted, so that one validation path serves
    every App and the framework never guesses that an App needs nothing.
    """


@dataclass(frozen=True)
class AppDefinition[DepsT, ConfigT: BaseModel]:
    """Everything a channel needs to know about an App without running it.

    ``DepsT`` is the app's own type for its application-scoped resource. The
    definition declares that its Tools require one of that type; it does not
    declare where one comes from. An entrypoint supplies that at composition
    time, and the type checker rejects a mismatch at that one site.

    An App whose Tools need no resource declares ``AppDefinition[None, ...]``.

    ``config`` is the opposite kind of type: one the framework validates against
    and projects. It is what this App requires of its host, and it is readable
    without acquiring anything.
    """

    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
