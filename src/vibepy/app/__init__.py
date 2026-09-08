"""The App: one unit of packaging and declaration."""

from vibepy.app.composition import (
    Lifespan,
    page_registry_for,
    page_runtime_for,
    tool_registry_for,
    tool_runtime_for,
)
from vibepy.app.entrypoint import (
    AppDescription,
    AppEntrypoint,
    PageDescription,
    ToolDescription,
)
from vibepy.app.model import AppDefinition, NoConfig

__all__ = [
    "AppDefinition",
    "AppDescription",
    "AppEntrypoint",
    "Lifespan",
    "NoConfig",
    "PageDescription",
    "ToolDescription",
    "page_registry_for",
    "page_runtime_for",
    "tool_registry_for",
    "tool_runtime_for",
]
