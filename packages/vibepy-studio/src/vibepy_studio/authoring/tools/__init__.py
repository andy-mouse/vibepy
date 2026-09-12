"""Studio's authoring operations: what a coding agent asks of the framework while writing an App.

Every handler here takes `ToolContext[object]`: authoring reads a source project
and runs the framework's own commands in that project's environment, so it
depends on nothing application-scoped and names none of Studio's resources
(`docs/architecture/authoring.md`, Authoring Core). `ToolContext` is read-only in
its dependency type, so these Tools compose into the App's own Tool sequence
unchanged.
"""

from collections.abc import Sequence

from vibepy_core.tool import Tool
from vibepy_studio.authoring.tools.inspection import (
    INSPECTION_TOOLS,
    inspect_app,
    inspect_framework,
)
from vibepy_studio.authoring.tools.invocation import INVOCATION_TOOLS, invoke_tool

AUTHORING_TOOLS: Sequence[Tool[object]] = [*INSPECTION_TOOLS, *INVOCATION_TOOLS]

__all__ = ["AUTHORING_TOOLS", "inspect_app", "inspect_framework", "invoke_tool"]
