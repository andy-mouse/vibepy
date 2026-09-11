"""The App: one unit of packaging and declaration."""

from vibepy_core.app.composition import (
    Lifespan,
    page_registry_for,
    page_runtime_for,
    tool_registry_for,
    tool_runtime_for,
)
from vibepy_core.app.config import AppConfig, NoConfig, environment_for
from vibepy_core.app.entrypoint import (
    AppDescription,
    AppEntrypoint,
    PageDescription,
    ToolDescription,
)
from vibepy_core.app.group import APP_GROUP
from vibepy_core.app.model import AppDefinition
from vibepy_core.app.package import AppRef, describe_app, discover_apps, load_app

__all__ = [
    "APP_GROUP",
    "AppConfig",
    "AppDefinition",
    "AppDescription",
    "AppEntrypoint",
    "AppRef",
    "Lifespan",
    "NoConfig",
    "PageDescription",
    "ToolDescription",
    "describe_app",
    "discover_apps",
    "environment_for",
    "load_app",
    "page_registry_for",
    "page_runtime_for",
    "tool_registry_for",
    "tool_runtime_for",
]
