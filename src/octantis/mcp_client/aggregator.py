# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregator that presents N per-server MCPConnector plugins as a single facade.

Exists because the LangGraph workflow expects a single manager-like object
with `get_tools()`, `get_connected_servers()`, `get_degraded_servers()`, and
`is_degraded`. Per-server MCP plugins (Fork B=1) each own one SSE connection;
this facade fans out the calls without re-adding a monolithic manager.
"""

from __future__ import annotations

from typing import Any, Protocol


class _PerServerMCPPlugin(Protocol):
    name: str

    def get_raw_tools(self) -> list[Any]: ...
    def get_connected_servers(self) -> list[str]: ...
    def get_degraded_servers(self) -> list[str]: ...
    def is_degraded(self) -> bool: ...


class AggregatedMCPManager:
    """Fan-out facade over per-server MCP plugins.

    The workflow is already wired through this minimal surface so swapping
    the old `MCPClientManager` for an aggregator requires no node-level
    changes.
    """

    def __init__(self, plugins: list[_PerServerMCPPlugin]) -> None:
        self._plugins = list(plugins)

    def get_tools(self) -> list[Any]:
        tools: list[Any] = []
        for p in self._plugins:
            tools.extend(p.get_raw_tools())
        return tools

    def get_connected_servers(self) -> list[str]:
        servers: list[str] = []
        for p in self._plugins:
            servers.extend(p.get_connected_servers())
        return servers

    def get_degraded_servers(self) -> list[str]:
        degraded: list[str] = []
        for p in self._plugins:
            degraded.extend(p.get_degraded_servers())
        return degraded

    @property
    def is_degraded(self) -> bool:
        if not self._plugins:
            return True
        return any(p.is_degraded() for p in self._plugins)
