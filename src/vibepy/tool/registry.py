"""Storage of bound Tools, and of the declarations registered with them."""

from pydantic import BaseModel

from vibepy.errors import ToolNotFoundError
from vibepy.tool.model import Tool, ToolDefinition
from vibepy.tool.runtime import BoundTool, bind


class ToolRegistry:
    """Maps a Tool name to the Tool registered under it. Storage only.

    The bound callable and the declaration are stored separately because
    binding erases the handler's type parameters into one uniform callable
    type, while a ToolDefinition holds no callable: its fields are read
    positions, so a frozen ToolDefinition is covariant in both parameters and
    a concrete declaration is storable as ``ToolDefinition[BaseModel,
    BaseModel]`` without ``Any`` or ``cast``.
    """

    def __init__(self) -> None:
        self._bound: dict[str, BoundTool] = {}
        self._declarations: dict[str, ToolDefinition[BaseModel, BaseModel]] = {}

    def register[InputT: BaseModel, OutputT: BaseModel](self, tool: Tool[InputT, OutputT]) -> None:
        name = tool.definition.name
        self._bound[name] = bind(tool)
        self._declarations[name] = tool.definition

    def resolve(self, name: str) -> BoundTool:
        bound = self._bound.get(name)
        if bound is None:
            raise ToolNotFoundError(name)
        return bound

    def definitions(self) -> tuple[ToolDefinition[BaseModel, BaseModel], ...]:
        """Every registered declaration, in registration order.

        A channel adapter projects these into its own discovery format, which
        is enumeration rather than lookup.
        """
        return tuple(self._declarations.values())
