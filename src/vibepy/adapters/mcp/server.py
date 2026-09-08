"""The MCP server an agent talks to, and the single call path behind it.

The adapter projects Tool declarations, exposes them for discovery, translates
arguments into a ToolRuntime invocation and translates results back. It owns no
business logic and creates no invocation context; ToolRuntime does that.

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
from vibepy.app.runtime import AppRuntime
from vibepy.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    to_error_info,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _no_lifespan(server: Server[None]) -> AsyncGenerator[None]:
    """Create no app-scoped state; AppRuntime owns that.

    Declared only so the server's lifespan result type is ``None``. The SDK's
    default lifespan is typed as yielding ``dict[str, Any]``, which would put
    ``Any`` into this module's public return type.
    """
    yield None


def _payload(error: Exception) -> dict[str, object]:
    """The framework's own description of a failure, in the form an agent reads.

    Both MCP failure paths carry it, so the Agent channel reports one failure one
    way whether the protocol answers with an error or with a result.
    """
    info = to_error_info(error)
    return {
        "code": info.code,
        "category": info.category.value,
        "message": info.message,
        "details": dict(info.details),
    }


def _failure(error: Exception) -> types.CallToolResult:
    """A failure the agent can read and act on, rather than a protocol error.

    The payload travels as text rather than as structured content: a Tool declares
    an output schema, and the specification requires structured results to conform
    to it.
    """
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(_payload(error)))],
        is_error=True,
    )


def build_mcp_server[DepsT](app: AppRuntime[DepsT]) -> Server[None]:
    """Build the MCP projection of one App's Tools.

    Constructed from the AppRuntime rather than from a registry and a runtime, so
    the Agent channel provably addresses the same running App as the Web channel.
    The registry answers what Tools exist, which is enumeration; ToolRuntime runs
    them, which is the framework's only invocation path.
    """
    registry = app.tool_registry
    runtime = app.tool_runtime

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
            raise MCPError(types.INVALID_PARAMS, str(error), _payload(error)) from error
        except ToolInputValidationError as error:
            return _failure(error)
        except ToolOutputValidationError as error:
            logger.error("Tool %r returned output its own model rejected", params.name)
            return _failure(error)
        # Broad on purpose: an app defect must not surface as a protocol error.
        except Exception as error:
            logger.exception("Tool %r raised", params.name)
            return _failure(error)
        data = result.model_dump(by_alias=True, mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(data))],
            structured_content=data,
        )

    return Server(
        app.definition.app_id,
        version=app.definition.version,
        lifespan=_no_lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
