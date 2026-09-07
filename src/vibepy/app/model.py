"""Declaration of an App. Static: it holds no live resource and no runtime state."""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


@dataclass(frozen=True)
class AppDefinition[DepsT]:
    """Everything AppRuntime needs to compose one running App.

    ``lifespan`` is a factory returning an async context manager rather than a
    live one. A definition that held a live resource could not be a declaration,
    and one definition would yield runtimes that shared state; a factory yields
    runtimes isolated from one another by default.

    What precedes the context manager's ``yield`` runs while the runtime is
    STARTING, what follows runs while it is STOPPING. Acquisition and release
    cannot be declared apart, which is what lets the framework release a resource
    whose type it does not know. See
    `docs/decisions/ADR-018-the-app-scoped-resource-is-an-async-context-manager.md`.

    ``DepsT`` is the app's own type for its application-scoped resource. An App
    that has none declares ``AppDefinition[None]`` with a lifespan yielding
    ``None``; no default is provided, because the framework does not guess that an
    App is stateless.
    """

    app_id: str
    name: str
    version: str
    lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
