"""MCP Client module — manages SSE connections to MCP servers."""

from octantis.mcp_client.manager import (
    MCPClientManager,
    MCPServerConfig,
    SlotValidationError,
)

__all__ = ["MCPClientManager", "MCPServerConfig", "SlotValidationError"]
