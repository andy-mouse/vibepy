"""Storage of Tools under their names."""

from vibepy_core.errors import ToolNotFoundError
from vibepy_core.tool.runtime import Tool


class ToolRegistry[DepsT]:
    """Maps a Tool name to the Tool registered under it. Storage only.

    The declaration is still stored inside the Tool as
    ``ToolDefinition[BaseModel, BaseModel]``, because a Tool carries its own —
    its fields are read positions, so a frozen ToolDefinition is covariant in
    both parameters and a concrete declaration is assignable without ``Any`` or
    ``cast``.
    """

    def __init__(self) -> None:
        """Start with no Tool registered."""
        self._tools: dict[str, Tool[DepsT]] = {}

    def register(self, tool: Tool[DepsT]) -> None:
        """Register `tool` under its own name, replacing any earlier one."""
        self._tools[tool.definition.name] = tool

    def resolve(self, name: str) -> Tool[DepsT]:
        """Return the Tool registered under `name`.

        Raises:
            ToolNotFoundError: no Tool is registered under that name.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool
