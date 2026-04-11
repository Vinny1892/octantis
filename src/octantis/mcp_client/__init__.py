"""MCP Client module — manages SSE connections to MCP servers."""

from octantis.mcp_client.manager import (
    MCPServerConfig,
    MCPClientManager,
    SlotValidationError,
)

__all__ = ["MCPServerConfig", "MCPClientManager", "SlotValidationError"]
