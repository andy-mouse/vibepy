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
from vibepy.app.package import APP_GROUP, AppRef, discover_apps

__all__ = [
    "APP_GROUP",
    "AppDefinition",
    "AppDescription",
    "AppEntrypoint",
    "AppRef",
    "Lifespan",
    "NoConfig",
    "PageDescription",
    "ToolDescription",
    "discover_apps",
    "page_registry_for",
    "page_runtime_for",
    "tool_registry_for",
    "tool_runtime_for",
]
