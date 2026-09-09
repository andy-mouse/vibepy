"""Projection of a Tool declaration into an MCP Tool definition.

The direction is always framework declaration to MCP, so schemas are derived
from the declaration's Pydantic models and never written by hand.
"""

from mcp import types
from pydantic import BaseModel

from vibepy_core.tool.model import ToolDefinition


def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool:
    """Project one declaration. Only fields with a source in ToolDefinition are set.

    The output schema is the model's serialization schema, because the payload a
    channel sends is a serialization dump: ADR-007 requires that the published
    schema and the returned value cannot diverge, and the MCP specification
    requires a structured result to conform to the schema declared here. The
    input schema stays the validation schema, because an argument mapping is
    validated against it.
    """
    return types.Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.input_model.model_json_schema(),
        output_schema=definition.output_model.model_json_schema(mode="serialization"),
    )
