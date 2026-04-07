"""Unit tests for the MCP Client Manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.config import GrafanaMCPSettings, InvestigationSettings, K8sMCPSettings
from octantis.mcp_client.manager import MCPClientManager


def _make_settings(
    grafana_url: str | None = "http://grafana-mcp:8080",
    grafana_api_key: str | None = "test-api-key",
    k8s_url: str | None = None,
) -> tuple[GrafanaMCPSettings, K8sMCPSettings, InvestigationSettings]:
    grafana = GrafanaMCPSettings(url=grafana_url, api_key=grafana_api_key)
    k8s = K8sMCPSettings(url=k8s_url)
    investigation = InvestigationSettings(query_timeout_seconds=5)
    return grafana, k8s, investigation


def _mock_sse_context():
    """Return an async context manager mock that yields (read_stream, write_stream)."""
    read_stream = MagicMock()
    write_stream = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=(read_stream, write_stream))
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_session_context():
    """Return an async context manager mock for ClientSession."""
    session = AsyncMock()
    session.initialize = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, session


@pytest.mark.asyncio
@patch("octantis.mcp_client.manager.load_mcp_tools")
@patch("octantis.mcp_client.manager.ClientSession")
@patch("octantis.mcp_client.manager.sse_client")
async def test_connect_grafana_success(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    """Successful connection to Grafana MCP loads tools and is not degraded."""
    grafana, k8s, investigation = _make_settings()

    sse_cm = _mock_sse_context()
    mock_sse_client.return_value = sse_cm

    session_cm, session = _mock_session_context()
    mock_client_session.return_value = session_cm

    fake_tool = MagicMock(name="prometheus_query")
    mock_load_tools.return_value = [fake_tool]

    manager = MCPClientManager(grafana, k8s, investigation)
    await manager.connect()

    assert not manager.is_degraded
    assert manager.get_degraded_servers() == []
    assert len(manager.get_tools()) == 1
    assert manager.get_tools()[0] is fake_tool

    mock_sse_client.assert_called_once_with(
        url="http://grafana-mcp:8080",
        headers={"Authorization": "Bearer test-api-key"},
        timeout=60,
    )
    session.initialize.assert_awaited_once()
    mock_load_tools.assert_awaited_once_with(session)

    await manager.close()


@pytest.mark.asyncio
@patch("octantis.mcp_client.manager.load_mcp_tools")
@patch("octantis.mcp_client.manager.ClientSession")
@patch("octantis.mcp_client.manager.sse_client")
async def test_get_tools_returns_tools_from_all_servers(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    """Tools from both Grafana and K8s servers are aggregated."""
    grafana, _, investigation = _make_settings(k8s_url="http://k8s-mcp:8080")
    k8s = K8sMCPSettings(url="http://k8s-mcp:8080")

    sse_cm = _mock_sse_context()
    mock_sse_client.return_value = sse_cm

    session_cm, _session = _mock_session_context()
    mock_client_session.return_value = session_cm

    grafana_tool = MagicMock(name="prometheus_query")
    k8s_tool = MagicMock(name="kubectl_get")
    mock_load_tools.side_effect = [[grafana_tool], [k8s_tool]]

    manager = MCPClientManager(grafana, k8s, investigation)
    await manager.connect()

    tools = manager.get_tools()
    assert len(tools) == 2
    assert grafana_tool in tools
    assert k8s_tool in tools

    await manager.close()


@pytest.mark.asyncio
@patch("octantis.mcp_client.manager.load_mcp_tools")
@patch("octantis.mcp_client.manager.ClientSession")
@patch("octantis.mcp_client.manager.sse_client")
async def test_degraded_when_grafana_unreachable(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    """Manager is degraded when Grafana MCP connection fails."""
    grafana, k8s, investigation = _make_settings()

    mock_sse_client.return_value.__aenter__ = AsyncMock(
        side_effect=ConnectionError("connection refused")
    )

    manager = MCPClientManager(grafana, k8s, investigation)
    await manager.connect()

    assert manager.is_degraded
    assert "grafana" in manager.get_degraded_servers()
    assert manager.get_tools() == []

    await manager.close()


@pytest.mark.asyncio
async def test_k8s_not_configured_no_error() -> None:
    """K8s MCP not configured produces no error and no tools."""
    grafana, k8s, investigation = _make_settings(
        grafana_url=None,
        grafana_api_key=None,
        k8s_url=None,
    )

    manager = MCPClientManager(grafana, k8s, investigation)
    await manager.connect()

    # Grafana is degraded because url is None, K8s is simply skipped
    assert "grafana" in manager.get_degraded_servers()
    assert "k8s" not in manager.get_degraded_servers()
    assert manager.get_tools() == []

    await manager.close()


@pytest.mark.asyncio
async def test_missing_api_key_logs_error_and_degrades(caplog: pytest.LogCaptureFixture) -> None:
    """Missing Grafana API key marks server as degraded."""
    grafana, k8s, investigation = _make_settings(
        grafana_url="http://grafana-mcp:8080",
        grafana_api_key=None,
    )

    manager = MCPClientManager(grafana, k8s, investigation)
    await manager.connect()

    assert manager.is_degraded
    assert "grafana" in manager.get_degraded_servers()
    assert manager.get_tools() == []

    await manager.close()


@pytest.mark.asyncio
@patch("octantis.mcp_client.manager.load_mcp_tools")
@patch("octantis.mcp_client.manager.ClientSession")
@patch("octantis.mcp_client.manager.sse_client")
async def test_close_clears_state(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    """After close(), tools and degraded lists are cleared."""
    grafana, k8s, investigation = _make_settings()

    sse_cm = _mock_sse_context()
    mock_sse_client.return_value = sse_cm

    session_cm, _session = _mock_session_context()
    mock_client_session.return_value = session_cm

    mock_load_tools.return_value = [MagicMock()]

    manager = MCPClientManager(grafana, k8s, investigation)
    await manager.connect()
    assert len(manager.get_tools()) == 1

    await manager.close()
    assert manager.get_tools() == []
    assert manager.get_degraded_servers() == []
    assert not manager.is_degraded
