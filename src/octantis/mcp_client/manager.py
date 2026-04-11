"""MCPClientManager — registry-based MCP server management with slot validation."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from octantis.config import MCPRetrySettings

log = structlog.get_logger(__name__)

MAX_PER_SLOT = 1
MIN_TOTAL = 1


@dataclass
class MCPServerConfig:
    """Describes a single MCP server connection."""

    name: str
    slot: Literal["observability", "platform"]
    url: str
    headers: dict[str, str] = field(default_factory=dict)


class SlotValidationError(Exception):
    """Raised when MCP slot validation fails."""


class MCPConnectionExhausted(Exception):
    """Raised when all retry attempts for an MCP connection are exhausted."""


class MCPClientManager:
    """Manages SSE connections to MCP servers via a registry pattern.

    Accepts a list of MCPServerConfig objects. Validates slot limits
    (min 1 total, max 1 per slot). Connects generically via SSE.
    """

    def __init__(
        self,
        configs: list[MCPServerConfig],
        retry_settings: MCPRetrySettings | None = None,
        query_timeout: int = 60,
    ) -> None:
        self._configs = configs
        self._retry = retry_settings or MCPRetrySettings()
        self._query_timeout = query_timeout

        self._sessions: dict[str, ClientSession] = {}
        self._tools: list[Any] = []
        self._degraded_servers: list[str] = []
        self._sse_contexts: dict[str, Any] = {}
        self._session_contexts: dict[str, Any] = {}

    def validate_slots(self) -> None:
        """Validate MCP slot configuration. Raises SlotValidationError on violation."""
        if len(self._configs) < MIN_TOTAL:
            raise SlotValidationError(
                "no MCP servers configured — at least one is required"
            )

        slots: dict[str, list[str]] = {}
        for cfg in self._configs:
            slots.setdefault(cfg.slot, []).append(cfg.name)

        for slot_name, names in slots.items():
            if len(names) > MAX_PER_SLOT:
                raise SlotValidationError(
                    f"multiple {slot_name} MCPs configured — limit is {MAX_PER_SLOT} per slot"
                )

        log.info(
            "mcp.slot_validation",
            observability_count=len(slots.get("observability", [])),
            platform_count=len(slots.get("platform", [])),
        )

    async def connect(self) -> None:
        """Connect to all configured MCP servers via SSE."""
        self.validate_slots()

        for cfg in self._configs:
            await self._connect_with_retry(cfg)

    async def _connect_with_retry(self, config: MCPServerConfig) -> None:
        """Attempt connection with exponential backoff retry."""
        max_attempts = self._retry.max_attempts
        base = self._retry.backoff_base

        for attempt in range(1, max_attempts + 1):
            try:
                await self._connect_server(
                    name=config.name,
                    url=config.url,
                    headers=config.headers,
                )
                # Clear degraded status from prior failed attempts
                if config.name in self._degraded_servers:
                    self._degraded_servers.remove(config.name)
                return
            except Exception as exc:
                if attempt < max_attempts:
                    backoff = base * (2 ** (attempt - 1))
                    log.warning(
                        "mcp.retry",
                        server=config.name,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        backoff_s=backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    log.error(
                        "mcp.retry_exhausted",
                        server=config.name,
                        attempts=max_attempts,
                    )
                    raise MCPConnectionExhausted(
                        f"all {max_attempts} connection attempts failed for {config.name}"
                    ) from exc

    async def _connect_server(
        self,
        name: str,
        url: str,
        headers: dict[str, str],
    ) -> None:
        """Open an SSE connection to *url* and load its tools."""
        timeout = self._query_timeout
        sse_cm = None
        session_cm = None
        try:
            sse_cm = sse_client(url=url, headers=headers, timeout=timeout)
            streams = await sse_cm.__aenter__()
            self._sse_contexts[name] = sse_cm

            session_cm = ClientSession(*streams)
            session = await session_cm.__aenter__()
            self._session_contexts[name] = session_cm

            await session.initialize()
            self._sessions[name] = session

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
            if session_cm is not None:
                with contextlib.suppress(Exception):
                    await session_cm.__aexit__(None, None, None)
                self._session_contexts.pop(name, None)
            if sse_cm is not None:
                with contextlib.suppress(Exception):
                    await sse_cm.__aexit__(None, None, None)
                self._sse_contexts.pop(name, None)
            raise

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

    def get_connected_servers(self) -> list[str]:
        """Return list of successfully connected server names."""
        return list(self._sessions.keys())

    @property
    def is_degraded(self) -> bool:
        """True if any MCP server is unavailable."""
        return len(self._degraded_servers) > 0
