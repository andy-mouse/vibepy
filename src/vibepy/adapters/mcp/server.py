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

from vibepy.adapters.mcp.projection import to_mcp_tool
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
        result = await runtime.invoke(params.name, params.arguments or {})
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
