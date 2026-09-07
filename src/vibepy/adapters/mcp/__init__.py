"""The Agent channel: framework Tools projected onto MCP."""

from vibepy.adapters.mcp.projection import to_mcp_tool
from vibepy.adapters.mcp.server import build_mcp_server

__all__ = ["build_mcp_server", "to_mcp_tool"]
