"""Per-server MCP connector plugins (Fork B=1: one plugin per server, SRP).

Each plugin wraps exactly one MCP server (grafana, k8s, docker, aws) and
implements the SDK `MCPConnector` Protocol. Replaces the unified
`MCPConnectorPlugin` that wrapped `MCPClientManager` wholesale.

The plugins share a single-server SSE connection backed by the existing
`MCPClientManager` (reused with a 1-config list); each plugin owns its
own manager instance so failures are isolated.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

import structlog
from octantis_plugin_sdk import Tool

from octantis.mcp_client.manager import MCPClientManager, MCPServerConfig

log = structlog.get_logger(__name__)


class _BaseMCPPlugin:
    """Shared lifecycle for per-server MCP plugins.

    Subclasses must define `name`, `slot`, and implement `_build_server_config`
    returning a MCPServerConfig or None (disabled).
    """

    name: str = ""
    slot: str = ""

    def __init__(self) -> None:
        self._manager: MCPClientManager | None = None

    def _build_server_config(self) -> MCPServerConfig | None:  # pragma: no cover — abstract
        raise NotImplementedError

    def setup(self, config: dict[str, Any]) -> None:
        from octantis.config import settings

        server_cfg = self._build_server_config()
        if server_cfg is None:
            self._manager = None
            log.info("mcp_plugin.disabled", server=self.name)
            return

        self._manager = MCPClientManager(
            configs=[server_cfg],
            retry_settings=settings.mcp_retry,
            query_timeout=settings.investigation.timeout_seconds,
        )

    def teardown(self) -> None:
        self._manager = None

    async def connect(self) -> None:
        if self._manager is None:
            return
        await self._manager.connect()

    async def close(self) -> None:
        if self._manager is None:
            return
        await self._manager.close()

    def get_tools(self) -> list[Tool]:
        if self._manager is None:
            return []
        return [
            Tool(
                name=t.name,
                description=t.description or "",
                datasource=_classify_tool(t.name),
                invoke=t,
            )
            for t in self._manager.get_tools()
        ]

    def get_raw_tools(self) -> list[Any]:
        if self._manager is None:
            return []
        return self._manager.get_tools()

    def is_degraded(self) -> bool:
        if self._manager is None:
            return True
        return self._manager.is_degraded

    def get_connected_servers(self) -> list[str]:
        if self._manager is None:
            return []
        return self._manager.get_connected_servers()

    def get_degraded_servers(self) -> list[str]:
        if self._manager is None:
            return []
        return self._manager.get_degraded_servers()

    @property
    def manager(self) -> MCPClientManager | None:
        return self._manager


class GrafanaMCPPlugin(_BaseMCPPlugin):
    """MCPConnector plugin for the Grafana MCP server (observability slot)."""

    name = "grafana-mcp"
    slot = "observability"

    def _build_server_config(self) -> MCPServerConfig | None:
        from octantis.config import settings

        if not settings.grafana_mcp.url:
            return None
        headers: dict[str, str] = {}
        if settings.grafana_mcp.api_key:
            headers["Authorization"] = f"Bearer {settings.grafana_mcp.api_key}"
        return MCPServerConfig(
            name="grafana",
            slot="observability",
            url=settings.grafana_mcp.url,
            headers=headers,
        )


class K8sMCPPlugin(_BaseMCPPlugin):
    """MCPConnector plugin for the Kubernetes MCP server (platform slot)."""

    name = "k8s-mcp"
    slot = "platform"

    def _build_server_config(self) -> MCPServerConfig | None:
        from octantis.config import settings

        if not settings.k8s_mcp.url:
            return None
        return MCPServerConfig(
            name="k8s",
            slot="platform",
            url=settings.k8s_mcp.url,
        )


class DockerMCPPlugin(_BaseMCPPlugin):
    """MCPConnector plugin for the Docker MCP server (platform slot)."""

    name = "docker-mcp"
    slot = "platform"

    def _build_server_config(self) -> MCPServerConfig | None:
        from octantis.config import settings

        if not settings.docker_mcp.url:
            return None
        headers: dict[str, str] = {}
        if settings.docker_mcp.headers:
            with contextlib.suppress(json.JSONDecodeError):
                headers = json.loads(settings.docker_mcp.headers)
        return MCPServerConfig(
            name="docker",
            slot="platform",
            url=settings.docker_mcp.url,
            headers=headers,
        )


class AWSMCPPlugin(_BaseMCPPlugin):
    """MCPConnector plugin for the AWS MCP server (platform slot)."""

    name = "aws-mcp"
    slot = "platform"

    def _build_server_config(self) -> MCPServerConfig | None:
        from octantis.config import settings

        if not settings.aws_mcp.url:
            return None
        headers: dict[str, str] = {}
        if settings.aws_mcp.headers:
            with contextlib.suppress(json.JSONDecodeError):
                headers = json.loads(settings.aws_mcp.headers)
        return MCPServerConfig(
            name="aws",
            slot="platform",
            url=settings.aws_mcp.url,
            headers=headers,
        )


def _classify_tool(tool_name: str) -> str:
    name_lower = tool_name.lower()
    if "promql" in name_lower or "prometheus" in name_lower or "metric" in name_lower:
        return "promql"
    if "logql" in name_lower or "loki" in name_lower or "log" in name_lower:
        return "logql"
    if "k8s" in name_lower or "kube" in name_lower or "pod" in name_lower:
        return "k8s"
    if "docker" in name_lower or "container" in name_lower:
        return "docker"
    if (
        "aws" in name_lower
        or "ec2" in name_lower
        or "cloudwatch" in name_lower
        or "ecs" in name_lower
    ):
        return "aws"
    return "promql"
