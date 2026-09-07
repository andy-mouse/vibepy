"""Storage of bound Tools under their names."""

from pydantic import BaseModel

from vibepy.errors import ToolNotFoundError
from vibepy.tool.model import Tool
from vibepy.tool.runtime import BoundTool, bind


class ToolRegistry:
    """Maps a Tool name to its bound callable. Storage only."""

    def __init__(self) -> None:
        self._bound: dict[str, BoundTool] = {}

    def register[InputT: BaseModel, OutputT: BaseModel](self, tool: Tool[InputT, OutputT]) -> None:
        self._bound[tool.definition.name] = bind(tool)

    def resolve(self, name: str) -> BoundTool:
        bound = self._bound.get(name)
        if bound is None:
            raise ToolNotFoundError(name)
        return bound
