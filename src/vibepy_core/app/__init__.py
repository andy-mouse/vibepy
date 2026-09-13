"""The App: one unit of packaging and declaration.

This surface follows the root's rule: declarations and descriptions, not the
operations that read or import a distribution. `docs/architecture/app-model.md`,
"The import surface", says where those are reached; ADR-035 says why.
"""

from vibepy_core.app._composition import (
    Lifespan,
    page_registry_for,
    page_runtime_for,
    tool_registry_for,
    tool_runtime_for,
)
from vibepy_core.app._model import AppDefinition
from vibepy_core.app._record import WindowRecord, read_window_record
from vibepy_core.app.config import (
    AppConfig,
    ConfigFieldDescription,
    ConfigFieldType,
    NoConfig,
)
from vibepy_core.app.entrypoint import (
    AppDescription,
    AppEntrypoint,
    DescribedApp,
    PageDescription,
    ToolDescription,
)

__all__ = [
    "AppConfig",
    "AppDefinition",
    "AppDescription",
    "AppEntrypoint",
    "ConfigFieldDescription",
    "ConfigFieldType",
    "DescribedApp",
    "Lifespan",
    "NoConfig",
    "PageDescription",
    "ToolDescription",
    "WindowRecord",
    "page_registry_for",
    "page_runtime_for",
    "read_window_record",
    "tool_registry_for",
    "tool_runtime_for",
]
