"""Projection of a Tool declaration into an MCP Tool definition.

The direction is always framework declaration to MCP, so schemas are derived
from the declaration's Pydantic models and never written by hand.
"""

from mcp import types
from pydantic import BaseModel

from vibepy_core.tool.model import ToolDefinition


def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool:
    """Project one declaration. Only fields with a source in ToolDefinition are set.

    The schemas are the declaration's own, so this adapter cannot publish a
    schema the other publishing surface does not. The MCP specification requires
    a structured result to conform to the schema declared here, which is what
    makes the output schema's mode the declaration's business rather than this
    adapter's.
    """
    return types.Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.input_schema(),
        output_schema=definition.output_schema(),
    )
