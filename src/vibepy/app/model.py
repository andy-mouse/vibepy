"""Declaration of an App. Static: it holds no live resource and no runtime state."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


@dataclass(frozen=True)
class AppDefinition[DepsT]:
    """Everything AppRuntime needs to compose one running App.

    ``create_dependencies`` is a factory rather than a resource. A definition that
    held a live resource could not be a declaration, and one definition would
    yield runtimes that shared state; a factory yields runtimes isolated from one
    another by default.

    ``DepsT`` is the app's own type for its application-scoped resource. An App
    that has none declares ``AppDefinition[None]`` with a factory returning
    ``None``; no default is provided, because the framework does not guess that an
    App is stateless.
    """

    app_id: str
    name: str
    version: str
    create_dependencies: Callable[[], DepsT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
