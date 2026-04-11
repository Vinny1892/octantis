"""Unit tests for the MCP Client Manager (registry pattern)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.config import MCPRetrySettings
from octantis.mcp_client.manager import (
    MCPClientManager,
    MCPServerConfig,
    SlotValidationError,
)


def _grafana_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="grafana",
        slot="observability",
        url="http://grafana-mcp:8080",
        headers={"Authorization": "Bearer test-api-key"},
    )


def _k8s_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="k8s",
        slot="platform",
        url="http://k8s-mcp:8080",
    )


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


# ─── Slot Validation Tests ───────────────────────────────────────────────────


def test_zero_mcp_configs_raises():
    manager = MCPClientManager(configs=[])
    with pytest.raises(SlotValidationError, match="no MCP servers"):
        manager.validate_slots()


def test_two_observability_mcp_raises():
    configs = [
        MCPServerConfig(name="grafana", slot="observability", url="http://a"),
        MCPServerConfig(name="elk", slot="observability", url="http://b"),
    ]
    manager = MCPClientManager(configs=configs)
    with pytest.raises(SlotValidationError, match="multiple observability"):
        manager.validate_slots()


def test_two_platform_mcp_raises():
    configs = [
        MCPServerConfig(name="docker", slot="platform", url="http://a"),
        MCPServerConfig(name="aws", slot="platform", url="http://b"),
    ]
    manager = MCPClientManager(configs=configs)
    with pytest.raises(SlotValidationError, match="multiple platform"):
        manager.validate_slots()


def test_one_observability_one_platform_valid():
    configs = [_grafana_config(), _k8s_config()]
    manager = MCPClientManager(configs=configs)
    manager.validate_slots()


def test_single_mcp_valid():
    configs = [_grafana_config()]
    manager = MCPClientManager(configs=configs)
    manager.validate_slots()


# ─── Connection Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("octantis.mcp_client.manager.load_mcp_tools")
@patch("octantis.mcp_client.manager.ClientSession")
@patch("octantis.mcp_client.manager.sse_client")
async def test_connect_success(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    sse_cm = _mock_sse_context()
    mock_sse_client.return_value = sse_cm

    session_cm, session = _mock_session_context()
    mock_client_session.return_value = session_cm

    fake_tool = MagicMock(name="prometheus_query")
    mock_load_tools.return_value = [fake_tool]

    manager = MCPClientManager(configs=[_grafana_config()])
    await manager.connect()

    assert not manager.is_degraded
    assert manager.get_degraded_servers() == []
    assert len(manager.get_tools()) == 1
    assert manager.get_connected_servers() == ["grafana"]

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
async def test_tools_from_multiple_servers(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    sse_cm = _mock_sse_context()
    mock_sse_client.return_value = sse_cm

    session_cm, _session = _mock_session_context()
    mock_client_session.return_value = session_cm

    grafana_tool = MagicMock(name="prometheus_query")
    k8s_tool = MagicMock(name="kubectl_get")
    mock_load_tools.side_effect = [[grafana_tool], [k8s_tool]]

    manager = MCPClientManager(configs=[_grafana_config(), _k8s_config()])
    await manager.connect()

    tools = manager.get_tools()
    assert len(tools) == 2
    assert grafana_tool in tools
    assert k8s_tool in tools

    await manager.close()


@pytest.mark.asyncio
async def test_connect_fails_exhausted_retries() -> None:
    """Connection failure after all retries raises and marks server degraded."""
    retry = MCPRetrySettings(max_attempts=1, backoff_base=0.01)

    with patch("octantis.mcp_client.manager.sse_client") as mock_sse:
        mock_sse.return_value.__aenter__ = AsyncMock(
            side_effect=ConnectionError("refused")
        )
        manager = MCPClientManager(
            configs=[_grafana_config()],
            retry_settings=retry,
        )
        # connect() calls validate_slots first, then retries
        # With max_attempts=1, it should raise MCPConnectionExhausted
        from octantis.mcp_client.manager import MCPConnectionExhausted

        with pytest.raises(MCPConnectionExhausted):
            await manager.connect()

        assert "grafana" in manager.get_degraded_servers()


@pytest.mark.asyncio
@patch("octantis.mcp_client.manager.load_mcp_tools")
@patch("octantis.mcp_client.manager.ClientSession")
@patch("octantis.mcp_client.manager.sse_client")
async def test_connect_succeeds_on_retry(
    mock_sse_client: MagicMock,
    mock_client_session: MagicMock,
    mock_load_tools: AsyncMock,
) -> None:
    """Connection fails on first attempt but succeeds on second."""
    sse_cm_fail = _mock_sse_context()
    sse_cm_fail.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))

    sse_cm_ok = _mock_sse_context()
    mock_sse_client.side_effect = [sse_cm_fail, sse_cm_ok]

    session_cm, _session = _mock_session_context()
    mock_client_session.return_value = session_cm

    mock_load_tools.return_value = [MagicMock(name="prometheus_query")]

    retry = MCPRetrySettings(max_attempts=2, backoff_base=0.01)
    manager = MCPClientManager(
        configs=[_grafana_config()],
        retry_settings=retry,
    )
    await manager.connect()

    assert not manager.is_degraded
    assert manager.get_connected_servers() == ["grafana"]
    assert len(manager.get_tools()) == 1

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
    sse_cm = _mock_sse_context()
    mock_sse_client.return_value = sse_cm

    session_cm, _session = _mock_session_context()
    mock_client_session.return_value = session_cm

    mock_load_tools.return_value = [MagicMock()]

    manager = MCPClientManager(configs=[_grafana_config()])
    await manager.connect()
    assert len(manager.get_tools()) == 1

    await manager.close()
    assert manager.get_tools() == []
    assert manager.get_degraded_servers() == []
    assert not manager.is_degraded
