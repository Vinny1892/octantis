# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP Client module — manages SSE connections to MCP servers."""

from octantis.mcp_client.manager import (
    MCPClientManager,
    MCPServerConfig,
    SlotValidationError,
)

__all__ = ["MCPClientManager", "MCPServerConfig", "SlotValidationError"]
