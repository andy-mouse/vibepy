"""The MCP server an agent talks to, and the single call path behind it.

``docs/architecture/adapters.md`` gives this adapter four jobs: project
declarations, expose them for discovery, translate arguments into a
ToolRuntime invocation, and translate results back. It owns no business logic
and creates no invocation context: ``docs/architecture/runtime.md`` reserves
that for ToolRuntime.

Building a Server is not running one. In stdio the agent platform owns the
process, so the entrypoint belongs to package metadata rather than here.
"""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.shared.exceptions import MCPError

from vibepy.adapters.mcp.projection import to_mcp_tool
from vibepy.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
)
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _no_lifespan(server: Server[None]) -> AsyncGenerator[None]:
    """Create no app-scoped state; AppRuntime owns that.

    Declared only so the server's lifespan result type is ``None``. The SDK's
    default lifespan is typed as yielding ``dict[str, Any]``, which would put
    ``Any`` into this module's public return type.
    """
    yield None


def _failure(message: str) -> types.CallToolResult:
    """A failure the agent can read and act on, rather than a protocol error."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], is_error=True
    )


def build_mcp_server(
    *, name: str, version: str, registry: ToolRegistry, runtime: ToolRuntime
) -> Server[None]:
    """Build the MCP projection of one App's Tools.

    The registry answers what Tools exist, which is enumeration; ToolRuntime
    runs them, which is the framework's only invocation path.
    """

    async def list_tools(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[to_mcp_tool(definition) for definition in registry.definitions()]
        )

    async def call_tool(
        ctx: ServerRequestContext[None], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            result = await runtime.invoke(params.name, params.arguments or {})
        except ToolNotFoundError as error:
            raise MCPError(types.INVALID_PARAMS, str(error)) from error
        except ToolInputValidationError as error:
            return _failure(str(error))
        except ToolOutputValidationError as error:
            logger.error("Tool %r returned output its own model rejected", params.name)
            return _failure(str(error))
        # Broad on purpose: an app defect must not surface as a protocol error.
        except Exception:
            logger.exception("Tool %r raised", params.name)
            return _failure(f"Tool {params.name!r} failed")
        data = result.model_dump(by_alias=True, mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(data))],
            structured_content=data,
        )

    return Server(
        name,
        version=version,
        lifespan=_no_lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
