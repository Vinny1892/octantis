"""Unit tests for main.py — plugin-based architecture.

Tests the registry-driven main.run() entry point, verifying that
receivers, processors, MCP connectors are loaded via the Plugin Registry
and events flow correctly through the pipeline.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.main import _build_notifier_config, _build_pipeline_config, _configure_logging, run

# ─── config helpers ──────────────────────────────────────────────────────


def test_build_pipeline_config():
    with patch("octantis.main.settings") as mock:
        mock.pipeline.cpu_threshold = 80.0
        mock.pipeline.memory_threshold = 85.0
        mock.pipeline.error_rate_threshold = 0.05
        mock.pipeline.benign_patterns_list = ["health", "readiness"]
        mock.pipeline.cooldown_seconds = 600.0
        mock.pipeline.cooldown_max_entries = 500

        config = _build_pipeline_config()

    assert config["trigger-filter"]["cpu_threshold"] == 80.0
    assert config["fingerprint-cooldown"]["cooldown_seconds"] == 600.0


def test_build_pipeline_config_defaults():
    with patch("octantis.main.settings") as mock:
        mock.pipeline.cpu_threshold = 75.0
        mock.pipeline.memory_threshold = 80.0
        mock.pipeline.error_rate_threshold = 0.01
        mock.pipeline.benign_patterns_list = []
        mock.pipeline.cooldown_seconds = 300.0
        mock.pipeline.cooldown_max_entries = 1000

        config = _build_pipeline_config()

    assert config["trigger-filter"]["cpu_threshold"] == 75.0
    assert config["trigger-filter"]["benign_patterns"] is None


def test_build_notifier_config_slack_enabled():
    with patch("octantis.main.settings") as mock:
        mock.slack.enabled = True
        mock.slack.webhook_url = "https://hooks.slack.com/test"
        mock.slack.bot_token = None
        mock.slack.channel = "#alerts"
        mock.discord.enabled = False

        config = _build_notifier_config()

    assert "slack" in config
    assert config["slack"]["webhook_url"] == "https://hooks.slack.com/test"


def test_build_notifier_config_discord_enabled():
    with patch("octantis.main.settings") as mock:
        mock.slack.enabled = False
        mock.discord.enabled = True
        mock.discord.webhook_url = "https://discord.com/webhook"

        config = _build_notifier_config()

    assert "discord" in config


def test_build_notifier_config_none_enabled():
    with patch("octantis.main.settings") as mock:
        mock.slack.enabled = False
        mock.discord.enabled = False

        config = _build_notifier_config()

    assert config == {}


# ─── _configure_logging ──────────────────────────────────────────────────


def test_configure_logging_tty():
    with (
        patch("octantis.main.settings") as mock_settings,
        patch("octantis.main.structlog") as mock_structlog,
        patch.object(sys, "stderr") as mock_stderr,
    ):
        mock_settings.log_level = "INFO"
        mock_stderr.isatty.return_value = True
        _configure_logging()
        mock_structlog.configure.assert_called_once()


def test_configure_logging_non_tty():
    with (
        patch("octantis.main.settings") as mock_settings,
        patch("octantis.main.structlog") as mock_structlog,
        patch.object(sys, "stderr") as mock_stderr,
    ):
        mock_settings.log_level = "DEBUG"
        mock_stderr.isatty.return_value = False
        _configure_logging()
        mock_structlog.configure.assert_called_once()


# ─── run() ────────────────────────────────────────────────────────────────


def _mock_settings():
    mock = MagicMock()
    mock.log_level = "INFO"
    mock.metrics.enabled = False
    mock.grafana_mcp.url = None
    mock.k8s_mcp.url = None
    mock.docker_mcp.url = None
    mock.aws_mcp.url = None
    mock.mcp_retry = MagicMock()
    mock.investigation.timeout_seconds = 60
    mock.platform.platform = None
    mock.otlp = MagicMock()
    mock.otlp.grpc_enabled = True
    mock.otlp.grpc_port = 4317
    mock.otlp.http_enabled = False
    mock.pipeline.cpu_threshold = 75.0
    mock.pipeline.memory_threshold = 80.0
    mock.pipeline.error_rate_threshold = 0.01
    mock.pipeline.benign_patterns_list = []
    mock.pipeline.cooldown_seconds = 300.0
    mock.pipeline.cooldown_max_entries = 1000
    mock.slack.enabled = False
    mock.discord.enabled = False
    mock.runtime.mode = "standalone"
    mock.runtime.workers = 5
    return mock


def _make_event():
    from octantis_plugin_sdk import Event as SDKEvent

    return SDKEvent(
        event_id="run-001",
        event_type="metric",
        source="api-server",
        resource={
            "service.name": "api-server",
            "k8s.namespace.name": "prod",
        },
        metrics=[{"name": "cpu_usage", "value": 95.0}],
    )


async def _events_from_list(events_list):
    for e in events_list:
        yield e


def _make_registry(events_list=None, filter_pass=True, cooldown_pass=True):
    from octantis.plugins.registry import LoadedPlugin, PluginType

    mock_filter_instance = MagicMock()

    async def filter_process(event):
        return event if filter_pass else None

    mock_filter_instance.process = filter_process

    mock_cooldown_instance = MagicMock()

    async def cooldown_process(event):
        return event if cooldown_pass else None

    mock_cooldown_instance.process = cooldown_process

    filter_plugin = LoadedPlugin(
        name="trigger-filter",
        type=PluginType.PROCESSOR,
        instance=mock_filter_instance,
        source_package="octantis",
        version="0.1.0",
        priority=100,
    )
    cooldown_plugin = LoadedPlugin(
        name="fingerprint-cooldown",
        type=PluginType.PROCESSOR,
        instance=mock_cooldown_instance,
        source_package="octantis",
        version="0.1.0",
        priority=200,
    )

    mock_receiver_instance = MagicMock()
    mock_receiver_instance.start = AsyncMock()
    mock_receiver_instance.stop = AsyncMock()
    mock_receiver_instance.events.return_value = _events_from_list(events_list or [])

    receiver_plugin = LoadedPlugin(
        name="otlp",
        type=PluginType.INGESTER,
        instance=mock_receiver_instance,
        source_package="octantis",
        version="0.1.0",
        priority=0,
    )

    registry = MagicMock()
    registry.plugins.side_effect = lambda ptype=None: {
        PluginType.PROCESSOR: [filter_plugin, cooldown_plugin],
        PluginType.MCP: [],
        PluginType.INGESTER: [receiver_plugin],
    }.get(ptype, [])
    registry.discover.return_value = [receiver_plugin, filter_plugin, cooldown_plugin]
    registry.setup_all.return_value = None
    registry.teardown_all.return_value = None
    return registry


@pytest.mark.asyncio
async def test_run_event_passes_pipeline():
    event = _make_event()
    mock_workflow = AsyncMock()
    mock_workflow.ainvoke.return_value = {
        "analysis": MagicMock(severity="CRITICAL"),
        "notifications_sent": ["slack"],
        "investigation": MagicMock(queries_executed=[], mcp_degraded=False),
    }

    mock_registry = _make_registry([event])

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal"),
    ):
        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()

    mock_workflow.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_run_event_dropped_by_filter():
    event = _make_event()
    mock_workflow = AsyncMock()
    mock_registry = _make_registry([event], filter_pass=False)

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
    ):
        await run()

    mock_workflow.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_run_event_dropped_by_cooldown():
    event = _make_event()
    mock_workflow = AsyncMock()
    mock_registry = _make_registry([event], cooldown_pass=False)

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
    ):
        await run()

    mock_workflow.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_run_workflow_error_doesnt_crash():
    event = _make_event()
    mock_workflow = AsyncMock()
    mock_workflow.ainvoke.side_effect = RuntimeError("LLM timeout")
    mock_registry = _make_registry([event])

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal"),
    ):
        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()


@pytest.mark.asyncio
async def test_run_metrics_server_started():
    mock_s = _mock_settings()
    mock_s.metrics.enabled = True
    mock_s.metrics.port = 9999

    mock_registry = _make_registry([])

    with (
        patch("octantis.main.settings", mock_s),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow"),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
        patch("octantis.metrics.start_metrics_server") as mock_start,
    ):
        await run()

    mock_start.assert_called_once_with(9999)


@pytest.mark.asyncio
async def test_run_with_mcp_connector():
    event = _make_event()
    mock_workflow = AsyncMock()
    mock_workflow.ainvoke.return_value = {
        "analysis": MagicMock(severity="CRITICAL"),
        "notifications_sent": [],
        "investigation": MagicMock(queries_executed=[], mcp_degraded=False),
    }

    mock_registry = _make_registry([event])

    mock_mcp_plugin = MagicMock()
    mock_mcp_plugin.instance.connect = AsyncMock()
    mock_mcp_plugin.instance.close = AsyncMock()
    mock_mcp_plugin.instance.is_degraded.return_value = False
    mock_mcp_plugin.instance.get_connected_servers.return_value = ["grafana"]
    mock_mcp_plugin.instance.get_degraded_servers.return_value = []
    mock_mcp_plugin.instance.manager = MagicMock()

    from octantis.plugins.registry import PluginType

    original_side_effect = mock_registry.plugins.side_effect

    def plugins_with_mcp(ptype=None):
        if ptype == PluginType.MCP:
            return [mock_mcp_plugin]
        return original_side_effect(ptype)

    mock_registry.plugins.side_effect = plugins_with_mcp

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal"),
    ):
        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()

    mock_mcp_plugin.instance.connect.assert_called_once()
    mock_mcp_plugin.instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_registry_teardown_called():
    mock_registry = _make_registry([])

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow"),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
    ):
        await run()

    mock_registry.teardown_all.assert_called_once()


@pytest.mark.asyncio
async def test_run_stop_event_breaks_loop():
    event = _make_event()

    mock_workflow = AsyncMock()
    mock_registry = _make_registry([event] * 5)

    signal_handlers = {}

    def capture_signal(sig, handler):
        signal_handlers[sig] = handler

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal", side_effect=capture_signal),
    ):
        from octantis.plugins.registry import PluginType

        for lp in mock_registry.plugins(PluginType.PROCESSOR):
            if lp.name == "trigger-filter":
                original_process = lp.instance.process

                def _make_process_with_stop(proc):
                    async def _wrapped(evt):
                        import signal as sig_mod

                        if sig_mod.SIGINT in signal_handlers:
                            signal_handlers[sig_mod.SIGINT]()
                        return await proc(evt)

                    return _wrapped

                process_with_stop = _make_process_with_stop(original_process)

                lp.instance.process = process_with_stop
                break

        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()


@pytest.mark.asyncio
async def test_run_calls_gate_before_setup():
    """registry.gate() must be called before registry.setup_all()."""
    from octantis.main import run

    event = _make_event()
    mock_workflow = AsyncMock()
    mock_workflow.ainvoke.return_value = {
        "analysis": MagicMock(severity="LOW"),
        "notifications_sent": [],
        "investigation": MagicMock(queries_executed=[], mcp_degraded=False),
    }
    mock_registry = _make_registry([event])

    call_order = []
    original_gate = mock_registry.gate
    original_setup = mock_registry.setup_all

    def tracking_gate(tier):
        call_order.append("gate")
        return original_gate(tier)

    def tracking_setup(cfg):
        call_order.append("setup_all")
        return original_setup(cfg)

    mock_registry.gate = tracking_gate
    mock_registry.setup_all = tracking_setup

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.PluginRegistry", return_value=mock_registry),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.resolve_tier"),
        patch("octantis.main.PLAN_TIER_INFO"),
    ):
        mock_detector = MagicMock()
        mock_detector.detect.return_value = MagicMock(event_id="x", source="s", metrics=[], logs=[])
        MockDetector.return_value = mock_detector
        await run()

    assert call_order.index("gate") < call_order.index("setup_all")
