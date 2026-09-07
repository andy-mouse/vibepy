"""Projection of a Tool declaration into an MCP Tool definition.

The direction is always framework declaration to MCP, so schemas are derived
from the declaration's Pydantic models and never written by hand.
"""

from mcp import types
from pydantic import BaseModel

from vibepy.tool.model import ToolDefinition


def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool:
    """Project one declaration. Only fields with a source in ToolDefinition are set."""
    return types.Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.input_model.model_json_schema(),
        output_schema=definition.output_model.model_json_schema(),
    )
