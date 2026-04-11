"""Unit tests for main.py — _build_mcp_configs, _build_pipeline, _configure_logging, run()."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.main import _build_mcp_configs, _build_pipeline, _configure_logging, run

# ─── _build_mcp_configs ───────────────────────────────────────────────────


def test_build_mcp_configs_grafana_only():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = "http://grafana:8080"
        mock.grafana_mcp.api_key = "test-key"
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = None
        mock.aws_mcp.url = None

        configs = _build_mcp_configs()

    assert len(configs) == 1
    assert configs[0].name == "grafana"
    assert configs[0].slot == "observability"
    assert configs[0].url == "http://grafana:8080"
    assert configs[0].headers["Authorization"] == "Bearer test-key"


def test_build_mcp_configs_grafana_no_api_key():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = "http://grafana:8080"
        mock.grafana_mcp.api_key = None
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = None
        mock.aws_mcp.url = None

        configs = _build_mcp_configs()

    assert len(configs) == 1
    assert configs[0].headers == {}


def test_build_mcp_configs_k8s():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = None
        mock.k8s_mcp.url = "http://k8s-mcp:3000"
        mock.docker_mcp.url = None
        mock.aws_mcp.url = None

        configs = _build_mcp_configs()

    assert len(configs) == 1
    assert configs[0].name == "k8s"
    assert configs[0].slot == "platform"


def test_build_mcp_configs_docker_with_headers():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = None
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = "http://docker-mcp:3000"
        mock.docker_mcp.headers = '{"X-Token": "abc"}'
        mock.aws_mcp.url = None

        configs = _build_mcp_configs()

    assert len(configs) == 1
    assert configs[0].name == "docker"
    assert configs[0].slot == "platform"
    assert configs[0].headers == {"X-Token": "abc"}


def test_build_mcp_configs_docker_invalid_headers():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = None
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = "http://docker-mcp:3000"
        mock.docker_mcp.headers = "not-json"
        mock.aws_mcp.url = None

        configs = _build_mcp_configs()

    assert len(configs) == 1
    assert configs[0].headers == {}


def test_build_mcp_configs_aws_with_headers():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = None
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = None
        mock.aws_mcp.url = "http://aws-mcp:3000"
        mock.aws_mcp.headers = '{"X-Region": "us-east-1"}'

        configs = _build_mcp_configs()

    assert len(configs) == 1
    assert configs[0].name == "aws"
    assert configs[0].slot == "platform"
    assert configs[0].headers == {"X-Region": "us-east-1"}


def test_build_mcp_configs_aws_invalid_headers():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = None
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = None
        mock.aws_mcp.url = "http://aws-mcp:3000"
        mock.aws_mcp.headers = "bad-json"

        configs = _build_mcp_configs()

    assert configs[0].headers == {}


def test_build_mcp_configs_all_platforms():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = "http://grafana:8080"
        mock.grafana_mcp.api_key = None
        mock.k8s_mcp.url = "http://k8s:3000"
        mock.docker_mcp.url = "http://docker:3000"
        mock.docker_mcp.headers = None
        mock.aws_mcp.url = "http://aws:3000"
        mock.aws_mcp.headers = None

        configs = _build_mcp_configs()

    assert len(configs) == 4
    names = {c.name for c in configs}
    assert names == {"grafana", "k8s", "docker", "aws"}


def test_build_mcp_configs_none():
    with patch("octantis.main.settings") as mock:
        mock.grafana_mcp.url = None
        mock.k8s_mcp.url = None
        mock.docker_mcp.url = None
        mock.aws_mcp.url = None

        configs = _build_mcp_configs()

    assert configs == []


# ─── _build_pipeline ──────────────────────────────────────────────────────


def test_build_pipeline_returns_filter_and_cooldown():
    with patch("octantis.main.settings") as mock:
        mock.pipeline.cpu_threshold = 80.0
        mock.pipeline.memory_threshold = 85.0
        mock.pipeline.error_rate_threshold = 0.05
        mock.pipeline.benign_patterns_list = ["health", "readiness"]
        mock.pipeline.cooldown_seconds = 600.0
        mock.pipeline.cooldown_max_entries = 500

        trigger_filter, cooldown = _build_pipeline()

    assert trigger_filter is not None
    assert cooldown is not None


def test_build_pipeline_defaults():
    with patch("octantis.main.settings") as mock:
        mock.pipeline.cpu_threshold = 75.0
        mock.pipeline.memory_threshold = 80.0
        mock.pipeline.error_rate_threshold = 0.01
        mock.pipeline.benign_patterns_list = []
        mock.pipeline.cooldown_seconds = 300.0
        mock.pipeline.cooldown_max_entries = 1000

        trigger_filter, cooldown = _build_pipeline()

    assert trigger_filter is not None
    assert cooldown is not None


# ─── _configure_logging ───────────────────────────────────────────────────


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
    """Return a mock settings object with all required attributes."""
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
    return mock


def _make_event():
    from octantis.models.event import InfraEvent, K8sResource, MetricDataPoint

    return InfraEvent(
        event_id="run-001",
        event_type="metric",
        source="api-server",
        resource=K8sResource(service_name="api-server", k8s_namespace="prod"),
        metrics=[MetricDataPoint(name="cpu_usage", value=95.0)],
    )


def _make_consumer(events_list):
    """Create a mock OTLPReceiver that yields events from a list."""

    async def _fake_events():
        for e in events_list:
            yield e

    mock = MagicMock()
    mock.events.return_value = _fake_events()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_run_event_passes_pipeline():
    """An event that passes filter and cooldown gets processed by the workflow."""
    event = _make_event()

    mock_consumer = _make_consumer([event])

    mock_workflow = AsyncMock()
    mock_workflow.ainvoke.return_value = {
        "analysis": MagicMock(severity="CRITICAL"),
        "notifications_sent": ["slack"],
        "investigation": MagicMock(queries_executed=[], mcp_degraded=False),
    }

    mock_mcp_manager = AsyncMock()
    mock_mcp_manager.is_degraded = False

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.MCPClientManager", return_value=mock_mcp_manager),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.OTLPReceiver", return_value=mock_consumer),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal"),
        patch("octantis.main.TriggerFilter") as MockFilter,
        patch("octantis.main.FingerprintCooldown") as MockCooldown,
    ):
        mock_filter = MagicMock()
        mock_filter.should_investigate.return_value = True
        MockFilter.default.return_value = mock_filter

        mock_cooldown = MagicMock()
        mock_cooldown.should_investigate.return_value = True
        mock_cooldown.stats.return_value = {}
        MockCooldown.return_value = mock_cooldown

        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()

    mock_workflow.ainvoke.assert_called_once()
    mock_consumer.stop.assert_called_once()
    mock_mcp_manager.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_event_dropped_by_filter():
    """An event that fails the trigger filter is dropped."""
    event = _make_event()

    mock_consumer = _make_consumer([event])

    mock_workflow = AsyncMock()
    mock_mcp_manager = AsyncMock()
    mock_mcp_manager.is_degraded = False

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.MCPClientManager", return_value=mock_mcp_manager),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.OTLPReceiver", return_value=mock_consumer),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
        patch("octantis.main.TriggerFilter") as MockFilter,
        patch("octantis.main.FingerprintCooldown") as MockCooldown,
    ):
        mock_filter = MagicMock()
        mock_filter.should_investigate.return_value = False
        MockFilter.default.return_value = mock_filter

        mock_cooldown = MagicMock()
        MockCooldown.return_value = mock_cooldown

        await run()

    mock_workflow.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_run_event_dropped_by_cooldown():
    """An event that passes filter but fails cooldown is dropped."""
    event = _make_event()

    mock_consumer = _make_consumer([event])

    mock_workflow = AsyncMock()
    mock_mcp_manager = AsyncMock()
    mock_mcp_manager.is_degraded = False

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.MCPClientManager", return_value=mock_mcp_manager),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.OTLPReceiver", return_value=mock_consumer),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
        patch("octantis.main.TriggerFilter") as MockFilter,
        patch("octantis.main.FingerprintCooldown") as MockCooldown,
    ):
        mock_filter = MagicMock()
        mock_filter.should_investigate.return_value = True
        MockFilter.default.return_value = mock_filter

        mock_cooldown = MagicMock()
        mock_cooldown.should_investigate.return_value = False
        mock_cooldown.stats.return_value = {}
        MockCooldown.return_value = mock_cooldown

        await run()

    mock_workflow.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_run_workflow_error_doesnt_crash():
    """A workflow error is logged but doesn't crash the loop."""
    event = _make_event()

    mock_consumer = _make_consumer([event])

    mock_workflow = AsyncMock()
    mock_workflow.ainvoke.side_effect = RuntimeError("LLM timeout")

    mock_mcp_manager = AsyncMock()
    mock_mcp_manager.is_degraded = False

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.MCPClientManager", return_value=mock_mcp_manager),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.OTLPReceiver", return_value=mock_consumer),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal"),
        patch("octantis.main.TriggerFilter") as MockFilter,
        patch("octantis.main.FingerprintCooldown") as MockCooldown,
    ):
        mock_filter = MagicMock()
        mock_filter.should_investigate.return_value = True
        MockFilter.default.return_value = mock_filter

        mock_cooldown = MagicMock()
        mock_cooldown.should_investigate.return_value = True
        mock_cooldown.stats.return_value = {}
        MockCooldown.return_value = mock_cooldown

        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()  # Should not raise

    mock_consumer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_run_metrics_server_started():
    """Metrics server is started when enabled."""
    mock_consumer = _make_consumer([])

    mock_mcp_manager = AsyncMock()
    mock_mcp_manager.is_degraded = False

    mock_s = _mock_settings()
    mock_s.metrics.enabled = True
    mock_s.metrics.port = 9999

    with (
        patch("octantis.main.settings", mock_s),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.MCPClientManager", return_value=mock_mcp_manager),
        patch("octantis.main.build_workflow"),
        patch("octantis.main.OTLPReceiver", return_value=mock_consumer),
        patch("octantis.main.EnvironmentDetector"),
        patch("octantis.main.signal.signal"),
        patch("octantis.main.TriggerFilter") as MockFilter,
        patch("octantis.main.FingerprintCooldown") as MockCooldown,
        patch("octantis.metrics.start_metrics_server") as mock_start,
    ):
        MockFilter.default.return_value = MagicMock()
        mock_cooldown = MagicMock()
        mock_cooldown.stats.return_value = {}
        MockCooldown.return_value = mock_cooldown

        await run()

    mock_start.assert_called_once_with(9999)


@pytest.mark.asyncio
async def test_run_stop_event_breaks_loop():
    """Setting the stop event breaks the event loop."""
    event = _make_event()

    async def _infinite_events():
        for _ in range(5):  # safety limit
            yield event

    mock_consumer = MagicMock()
    mock_consumer.events.return_value = _infinite_events()
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()

    mock_workflow = AsyncMock()
    mock_mcp_manager = AsyncMock()
    mock_mcp_manager.is_degraded = False

    # Capture signal handler to call it
    signal_handlers = {}

    def capture_signal(sig, handler):
        signal_handlers[sig] = handler

    with (
        patch("octantis.main.settings", _mock_settings()),
        patch("octantis.main._configure_logging"),
        patch("octantis.main.MCPClientManager", return_value=mock_mcp_manager),
        patch("octantis.main.build_workflow", return_value=mock_workflow),
        patch("octantis.main.OTLPReceiver", return_value=mock_consumer),
        patch("octantis.main.EnvironmentDetector") as MockDetector,
        patch("octantis.main.signal.signal", side_effect=capture_signal),
        patch("octantis.main.TriggerFilter") as MockFilter,
        patch("octantis.main.FingerprintCooldown") as MockCooldown,
    ):
        mock_filter = MagicMock()

        def should_investigate_side_effect(ev):
            import signal as sig_mod

            if sig_mod.SIGINT in signal_handlers:
                signal_handlers[sig_mod.SIGINT]()
            return True

        mock_filter.should_investigate.side_effect = should_investigate_side_effect
        MockFilter.default.return_value = mock_filter

        mock_cooldown = MagicMock()
        mock_cooldown.should_investigate.return_value = True
        mock_cooldown.stats.return_value = {}
        MockCooldown.return_value = mock_cooldown

        mock_detector = MagicMock()
        mock_detector.detect.return_value = event
        MockDetector.return_value = mock_detector

        await run()

    mock_consumer.stop.assert_called_once()
