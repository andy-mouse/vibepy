"""Studio's authoring operations: what a coding agent asks of the framework while writing an App.

Every handler here takes `ToolContext[object]`: authoring reads a source project
and runs the framework's own commands in that project's environment, so it
depends on nothing application-scoped and names none of Studio's resources
(`docs/architecture/authoring.md`, Authoring Core). `ToolContext` is read-only in
its dependency type, so these Tools compose into the App's own Tool sequence
unchanged. `Tool` is invariant in that type, so each group is a function generic
in it rather than a constant: the declarations are built for the App composing
them, and the type variable is named once on purpose.
"""

from collections.abc import Sequence

from vibepy_core.tool import Tool
from vibepy_studio.authoring.tools.inspection import (
    inspect_app,
    inspect_framework,
    inspection_tools,
)
from vibepy_studio.authoring.tools.invocation import invocation_tools, invoke_tool


def authoring_tools[DepsT]() -> Sequence[Tool[DepsT]]:  # pyright: ignore[reportInvalidTypeVarUse]
    """Return every authoring Tool, for whatever dependency type the App composing them declares."""
    return [*inspection_tools(), *invocation_tools()]


__all__ = ["authoring_tools", "inspect_app", "inspect_framework", "invoke_tool"]
