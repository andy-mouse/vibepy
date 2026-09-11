"""The MCP server an agent talks to, and the single call path behind it.

The adapter projects Tool declarations, exposes them for discovery, translates
arguments into a ToolRuntime invocation and translates results back. It owns no
business logic and creates no invocation context; ToolRuntime does that.

Static state is read from the declaration and dynamic state from the SDK's own
request context, so the adapter holds no running state of its own.

Building a Server is not running one. In stdio the agent platform owns the
process, so the entrypoint belongs to package metadata rather than here.
"""

import json
import logging
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.shared.exceptions import MCPError

from vibepy_core.adapters.mcp.projection import to_mcp_tool
from vibepy_core.app.composition import Lifespan, tool_runtime_for
from vibepy_core.app.config import AppConfig
from vibepy_core.app.model import AppDefinition
from vibepy_core.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    to_error_info,
)
from vibepy_core.tool.runtime import ToolRuntime

logger = logging.getLogger(__name__)


def _payload(error: Exception) -> dict[str, object]:
    """Build the framework's own description of a failure, in the form an agent reads.

    Both MCP failure paths carry it, so the Agent channel reports one failure one
    way whether the protocol answers with an error or with a result.
    """
    return to_error_info(error).model_dump(mode="json")


def _failure(error: Exception) -> types.CallToolResult:
    """Report a failure the agent can read and act on, rather than a protocol error.

    The payload travels as text rather than as structured content: a Tool declares
    an output schema, and the specification requires structured results to conform
    to it.
    """
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(_payload(error)))],
        is_error=True,
    )


def build_mcp_server[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> Server[ToolRuntime[DepsT]]:
    """Build the MCP projection of one App's Tools."""

    @asynccontextmanager
    async def server_lifespan(
        server: Server[ToolRuntime[DepsT]],
    ) -> AsyncGenerator[ToolRuntime[DepsT]]:
        async with tool_runtime_for(definition, lifespan, config=config) as runtime:
            yield runtime

    async def list_tools(
        ctx: ServerRequestContext[ToolRuntime[DepsT]],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[to_mcp_tool(tool.definition) for tool in definition.tools]
        )

    async def call_tool(
        ctx: ServerRequestContext[ToolRuntime[DepsT]], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            result = await ctx.lifespan_context.invoke(params.name, params.arguments or {})
        except ToolNotFoundError as error:
            raise MCPError(types.INVALID_PARAMS, str(error), _payload(error)) from error
        except ToolInputValidationError as error:
            return _failure(error)
        except ToolOutputValidationError as error:
            logger.error("Tool %r returned output its own model rejected", params.name)
            return _failure(error)
        # Broad on purpose: a app defect must not surface as a protocol error.
        except Exception as error:
            logger.exception("Tool %r raised", params.name)
            return _failure(error)
        data = result.model_dump(by_alias=True, mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(data))],
            structured_content=data,
        )

    return Server(
        definition.app_id,
        version=definition.version,
        lifespan=server_lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
