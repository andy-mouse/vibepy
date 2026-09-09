"""Storage of Tools under their names."""

from pydantic import BaseModel

from vibepy_core.errors import ToolNotFoundError
from vibepy_core.tool.model import ToolDefinition
from vibepy_core.tool.runtime import Tool


class ToolRegistry[DepsT]:
    """Maps a Tool name to the Tool registered under it. Storage only.

    A Tool carries both its bound callable and its declaration, so one dictionary
    serves resolution and enumeration. The declaration is stored inside the Tool
    as ``ToolDefinition[BaseModel, BaseModel]``: its fields are read positions, so
    a frozen ToolDefinition is covariant in both parameters and a concrete
    declaration is assignable without ``Any`` or ``cast``.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool[DepsT]] = {}

    def register(self, tool: Tool[DepsT]) -> None:
        self._tools[tool.definition.name] = tool

    def resolve(self, name: str) -> Tool[DepsT]:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def definitions(self) -> tuple[ToolDefinition[BaseModel, BaseModel], ...]:
        """Every registered declaration, in registration order.

        A channel adapter projects these into its own discovery format, which is
        enumeration rather than lookup.
        """
        return tuple(tool.definition for tool in self._tools.values())
