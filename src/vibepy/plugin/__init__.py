"""The Plugin: one unit of packaging and declaration."""

from vibepy.plugin.composition import (
    Lifespan,
    page_registry_for,
    page_runtime_for,
    tool_registry_for,
    tool_runtime_for,
)
from vibepy.plugin.model import PluginDefinition

__all__ = [
    "Lifespan",
    "PluginDefinition",
    "page_registry_for",
    "page_runtime_for",
    "tool_registry_for",
    "tool_runtime_for",
]
