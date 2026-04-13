"""Tests for per-server MCP plugins (Fork B=1) + AggregatedMCPManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octantis_plugin_sdk import MCPConnector

from octantis.mcp_client.aggregator import AggregatedMCPManager
from octantis.plugins.builtins.mcp_plugins import (
    AWSMCPPlugin,
    DockerMCPPlugin,
    GrafanaMCPPlugin,
    K8sMCPPlugin,
    _classify_tool,
)


@pytest.fixture
def fake_settings():
    """Patch settings used inside mcp_plugins at setup()."""
    with patch("octantis.plugins.builtins.mcp_plugins.__import__") as _:
        yield


class TestProtocolConformance:
    @pytest.mark.parametrize("cls", [GrafanaMCPPlugin, K8sMCPPlugin, DockerMCPPlugin, AWSMCPPlugin])
    def test_each_plugin_satisfies_mcpconnector(self, cls):
        assert isinstance(cls(), MCPConnector)


class TestGrafanaPluginSetup:
    def test_setup_without_url_disables_manager(self):
        plugin = GrafanaMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.grafana_mcp.url = ""
            plugin.setup({})
        assert plugin.manager is None

    def test_setup_with_url_builds_manager(self):
        plugin = GrafanaMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.grafana_mcp.url = "http://grafana:8080"
            s.grafana_mcp.api_key = "tok"
            s.mcp_retry = MagicMock()
            s.investigation.timeout_seconds = 60
            plugin.setup({})
        assert plugin.manager is not None
        assert plugin.manager._configs[0].name == "grafana"
        assert plugin.manager._configs[0].headers["Authorization"] == "Bearer tok"


class TestK8sPluginSetup:
    def test_k8s_setup_no_url(self):
        plugin = K8sMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.k8s_mcp.url = ""
            plugin.setup({})
        assert plugin.manager is None

    def test_k8s_setup_ok(self):
        plugin = K8sMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.k8s_mcp.url = "http://k8s:8080"
            s.mcp_retry = MagicMock()
            s.investigation.timeout_seconds = 60
            plugin.setup({})
        assert plugin.manager._configs[0].slot == "platform"


class TestDockerAndAWSPluginSetup:
    def test_docker_parses_json_headers(self):
        plugin = DockerMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.docker_mcp.url = "http://docker:8080"
            s.docker_mcp.headers = '{"X-Api": "1"}'
            s.mcp_retry = MagicMock()
            s.investigation.timeout_seconds = 60
            plugin.setup({})
        assert plugin.manager._configs[0].headers == {"X-Api": "1"}

    def test_docker_bad_headers_are_tolerated(self):
        plugin = DockerMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.docker_mcp.url = "http://docker:8080"
            s.docker_mcp.headers = "not-json"
            s.mcp_retry = MagicMock()
            s.investigation.timeout_seconds = 60
            plugin.setup({})
        assert plugin.manager._configs[0].headers == {}

    def test_aws_ok(self):
        plugin = AWSMCPPlugin()
        with patch("octantis.config.settings") as s:
            s.aws_mcp.url = "http://aws:8080"
            s.aws_mcp.headers = ""
            s.mcp_retry = MagicMock()
            s.investigation.timeout_seconds = 60
            plugin.setup({})
        assert plugin.manager._configs[0].name == "aws"


class TestLifecycle:
    def test_teardown_clears_manager(self):
        plugin = GrafanaMCPPlugin()
        plugin._manager = MagicMock()
        plugin.teardown()
        assert plugin.manager is None

    @pytest.mark.asyncio
    async def test_connect_without_manager_is_noop(self):
        await GrafanaMCPPlugin().connect()

    @pytest.mark.asyncio
    async def test_connect_calls_manager(self):
        plugin = GrafanaMCPPlugin()
        plugin._manager = MagicMock()
        plugin._manager.connect = AsyncMock()
        await plugin.connect()
        plugin._manager.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_manager_is_noop(self):
        await GrafanaMCPPlugin().close()

    @pytest.mark.asyncio
    async def test_close_calls_manager(self):
        plugin = GrafanaMCPPlugin()
        plugin._manager = MagicMock()
        plugin._manager.close = AsyncMock()
        await plugin.close()
        plugin._manager.close.assert_called_once()


class TestAccessors:
    def test_no_manager_returns_empty_and_degraded(self):
        plugin = GrafanaMCPPlugin()
        assert plugin.get_tools() == []
        assert plugin.get_raw_tools() == []
        assert plugin.get_connected_servers() == []
        assert plugin.get_degraded_servers() == []
        assert plugin.is_degraded() is True

    def test_tools_converted_to_sdk_tools(self):
        plugin = GrafanaMCPPlugin()
        mock_tool = MagicMock()
        mock_tool.name = "query_prometheus"
        mock_tool.description = "PromQL"
        plugin._manager = MagicMock()
        plugin._manager.get_tools.return_value = [mock_tool]
        tools = plugin.get_tools()
        assert tools[0].name == "query_prometheus"
        assert tools[0].datasource == "promql"

    def test_is_degraded_delegates(self):
        plugin = K8sMCPPlugin()
        plugin._manager = MagicMock()
        plugin._manager.is_degraded = False
        assert plugin.is_degraded() is False


class TestClassifier:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("query_prometheus", "promql"),
            ("loki_logs", "logql"),
            ("list_pods", "k8s"),
            ("docker_inspect", "docker"),
            ("aws_ec2_status", "aws"),
            ("unknown", "promql"),
        ],
    )
    def test_classify(self, name, expected):
        assert _classify_tool(name) == expected


class TestAggregatedMCPManager:
    def _plugin(self, *, tools=None, connected=None, degraded=None, is_degraded=False):
        p = MagicMock()
        p.get_raw_tools.return_value = tools or []
        p.get_connected_servers.return_value = connected or []
        p.get_degraded_servers.return_value = degraded or []
        p.is_degraded.return_value = is_degraded
        return p

    def test_empty_is_degraded(self):
        agg = AggregatedMCPManager([])
        assert agg.is_degraded is True
        assert agg.get_tools() == []

    def test_tools_are_concatenated(self):
        t1, t2 = MagicMock(), MagicMock()
        agg = AggregatedMCPManager([self._plugin(tools=[t1]), self._plugin(tools=[t2])])
        assert agg.get_tools() == [t1, t2]

    def test_connected_and_degraded_aggregated(self):
        agg = AggregatedMCPManager(
            [
                self._plugin(connected=["grafana"]),
                self._plugin(connected=["k8s"], degraded=["docker"], is_degraded=True),
            ]
        )
        assert agg.get_connected_servers() == ["grafana", "k8s"]
        assert agg.get_degraded_servers() == ["docker"]
        assert agg.is_degraded is True

    def test_all_healthy(self):
        agg = AggregatedMCPManager(
            [self._plugin(is_degraded=False), self._plugin(is_degraded=False)]
        )
        assert agg.is_degraded is False
