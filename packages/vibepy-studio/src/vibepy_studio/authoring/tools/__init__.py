"""Studio's authoring operations: what a coding agent asks of the framework while writing an App."""

from collections.abc import Sequence

from vibepy_core.tool import Tool
from vibepy_studio.authoring.tools.inspection import (
    INSPECTION_TOOLS,
    inspect_app,
    inspect_framework,
)
from vibepy_studio.authoring.tools.invocation import INVOCATION_TOOLS, invoke_tool
from vibepy_studio.internals import StudioDeps

AUTHORING_TOOLS: Sequence[Tool[StudioDeps]] = [*INSPECTION_TOOLS, *INVOCATION_TOOLS]

__all__ = ["AUTHORING_TOOLS", "inspect_app", "inspect_framework", "invoke_tool"]
