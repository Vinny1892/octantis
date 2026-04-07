"""MCPClientManager — manages SSE connections to MCP servers and exposes tools."""

from __future__ import annotations

import contextlib
from typing import Any

import structlog
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from octantis.config import GrafanaMCPSettings, InvestigationSettings, K8sMCPSettings

log = structlog.get_logger(__name__)


class MCPClientManager:
    """Manages SSE connections to MCP servers and exposes tools."""

    def __init__(
        self,
        grafana_settings: GrafanaMCPSettings,
        k8s_settings: K8sMCPSettings,
        investigation_settings: InvestigationSettings,
    ) -> None:
        self._grafana_settings = grafana_settings
        self._k8s_settings = k8s_settings
        self._investigation_settings = investigation_settings

        self._sessions: dict[str, ClientSession] = {}
        self._tools: list[Any] = []
        self._degraded_servers: list[str] = []
        # Keep references to context managers so we can clean up
        self._sse_contexts: dict[str, Any] = {}
        self._session_contexts: dict[str, Any] = {}

    async def connect(self) -> None:
        """Connect to configured MCP servers via SSE.

        Logs ``mcp.connected`` on success or ``mcp.connection_failed`` on failure.
        A failed connection does not raise — the server is marked as degraded.
        """
        await self._connect_grafana()
        await self._connect_k8s()

    async def _connect_grafana(self) -> None:
        """Attempt to connect to the Grafana MCP server."""
        if not self._grafana_settings.url:
            log.warning("mcp.connection_failed", server="grafana", reason="url not configured")
            self._degraded_servers.append("grafana")
            return

        if not self._grafana_settings.api_key:
            log.error(
                "mcp.connection_failed",
                server="grafana",
                reason="api_key not configured",
            )
            self._degraded_servers.append("grafana")
            return

        headers = {"Authorization": f"Bearer {self._grafana_settings.api_key}"}
        await self._connect_server(
            name="grafana",
            url=self._grafana_settings.url,
            headers=headers,
        )

    async def _connect_k8s(self) -> None:
        """Attempt to connect to the K8s MCP server (optional)."""
        if not self._k8s_settings.url:
            log.debug("mcp.skipped", server="k8s", reason="url not configured")
            return

        await self._connect_server(name="k8s", url=self._k8s_settings.url, headers={})

    async def _connect_server(
        self,
        name: str,
        url: str,
        headers: dict[str, str],
    ) -> None:
        """Open an SSE connection to *url* and load its tools."""
        timeout = self._investigation_settings.timeout_seconds
        sse_cm = None
        session_cm = None
        try:
            # Enter the SSE client context manager
            sse_cm = sse_client(url=url, headers=headers, timeout=timeout)
            streams = await sse_cm.__aenter__()
            self._sse_contexts[name] = sse_cm

            # Create and initialise the MCP session
            session_cm = ClientSession(*streams)
            session = await session_cm.__aenter__()
            self._session_contexts[name] = session_cm

            await session.initialize()
            self._sessions[name] = session

            # Load tools as LangChain-compatible tools
            tools = await load_mcp_tools(session)
            self._tools.extend(tools)

            log.info(
                "mcp.connected",
                server=name,
                url=url,
                tool_count=len(tools),
            )
        except Exception:
            log.warning("mcp.connection_failed", server=name, url=url, exc_info=True)
            self._degraded_servers.append(name)
            # Clean up partially opened contexts to avoid orphaned SSE readers
            if session_cm is not None:
                with contextlib.suppress(Exception):
                    await session_cm.__aexit__(None, None, None)
                self._session_contexts.pop(name, None)
            if sse_cm is not None:
                with contextlib.suppress(Exception):
                    await sse_cm.__aexit__(None, None, None)
                self._sse_contexts.pop(name, None)

    async def close(self) -> None:
        """Close all SSE connections and sessions."""
        for name, session_cm in self._session_contexts.items():
            try:
                await session_cm.__aexit__(None, None, None)
            except Exception:
                log.warning("mcp.close_error", server=name, stage="session", exc_info=True)

        for name, sse_cm in self._sse_contexts.items():
            try:
                await sse_cm.__aexit__(None, None, None)
            except Exception:
                log.warning("mcp.close_error", server=name, stage="sse", exc_info=True)

        self._sessions.clear()
        self._session_contexts.clear()
        self._sse_contexts.clear()
        self._tools.clear()
        self._degraded_servers.clear()

    def get_tools(self) -> list[Any]:
        """Return all available MCP tools as LangChain-compatible tools."""
        return list(self._tools)

    def get_degraded_servers(self) -> list[str]:
        """Return list of MCP server names that failed to connect."""
        return list(self._degraded_servers)

    @property
    def is_degraded(self) -> bool:
        """True if any required MCP server (Grafana) is unavailable."""
        return "grafana" in self._degraded_servers
