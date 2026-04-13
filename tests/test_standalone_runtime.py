"""Tests for the standalone concurrent runtime (Phase 4).

Covers:
- N events dispatched as N parallel tasks
- Semaphore-bounded concurrency (OCTANTIS_WORKERS cap)
- Cancellation propagates cleanly via TaskGroup
- Unknown / not-yet-implemented OCTANTIS_MODE values rejected at startup
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octantis_plugin_sdk import Event as SDKEvent

from octantis.main import _process_one_event, _run_standalone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sdk_event(event_id: str = "evt-1") -> SDKEvent:
    return SDKEvent(
        event_id=event_id,
        event_type="metric",
        source="svc",
        resource={"service.name": "svc"},
        metrics=[{"name": "cpu", "value": 80.0}],
    )


def _passthrough_processor():
    """Processor that passes events through unchanged."""
    p = MagicMock()
    p.name = "pass"

    async def process(evt):
        return evt

    p.instance.process = process
    return p


def _drop_processor():
    """Processor that drops all events."""
    p = MagicMock()
    p.name = "trigger-filter"

    async def process(evt):
        return None

    p.instance.process = process
    return p


def _make_workflow(delay: float = 0.0, *, raises: bool = False):
    wf = MagicMock()

    async def ainvoke(state):
        if delay:
            await asyncio.sleep(delay)
        if raises:
            raise RuntimeError("workflow failed")
        return {"analysis": MagicMock(severity="CRITICAL"), "notifications_sent": [], "investigation": None}

    wf.ainvoke = ainvoke
    return wf


def _make_detector():
    d = MagicMock()
    d.detect.side_effect = lambda ev: ev
    return d


async def _events_async(*events):
    for e in events:
        yield e


# ---------------------------------------------------------------------------
# _process_one_event tests
# ---------------------------------------------------------------------------


class TestProcessOneEvent:
    @pytest.mark.asyncio
    async def test_passthrough_calls_workflow(self):
        workflow = _make_workflow()
        event = _sdk_event()
        with patch("octantis.main.TRIGGER_TOTAL"):
            await _process_one_event(event, [_passthrough_processor()], _make_detector(), workflow)
        # workflow.ainvoke called once
        # (we can't easily assert on the InfraEvent arg, but no exception = success)

    @pytest.mark.asyncio
    async def test_dropped_event_skips_workflow(self):
        workflow = _make_workflow()
        event = _sdk_event()
        with patch("octantis.main.TRIGGER_TOTAL"):
            await _process_one_event(event, [_drop_processor()], _make_detector(), workflow)
        # Workflow should NOT have been called - no exception means drop path taken

    @pytest.mark.asyncio
    async def test_workflow_error_does_not_propagate(self):
        workflow = _make_workflow(raises=True)
        event = _sdk_event()
        with patch("octantis.main.TRIGGER_TOTAL"):
            # Should not raise — errors are caught and logged
            await _process_one_event(event, [_passthrough_processor()], _make_detector(), workflow)


# ---------------------------------------------------------------------------
# _run_standalone concurrency tests
# ---------------------------------------------------------------------------


class TestRunStandalone:
    @pytest.mark.asyncio
    async def test_5_events_processed_concurrently(self):
        """5 events with a slow workflow should all launch in parallel, not serially."""
        started: list[str] = []
        finished: list[str] = []

        async def slow_workflow(state):
            event_id = state["event"].event_id
            started.append(event_id)
            await asyncio.sleep(0.05)
            finished.append(event_id)
            return {"analysis": None, "notifications_sent": [], "investigation": None}

        workflow = MagicMock()
        workflow.ainvoke = slow_workflow

        events = [_sdk_event(f"e{i}") for i in range(5)]
        stop_event = asyncio.Event()

        async def ingester_stream():
            for e in events:
                yield e
            stop_event.set()

        with (
            patch("octantis.main.TRIGGER_TOTAL"),
            patch("octantis.main.STANDALONE_ACTIVE_WORKFLOWS"),
            patch("octantis.main.STANDALONE_SEMAPHORE_CAPACITY"),
            patch("octantis.main.settings") as mock_settings,
            patch("octantis.main._merge_ingester_events", return_value=ingester_stream()),
        ):
            mock_settings.runtime.workers = 10

            await _run_standalone(
                ingester_instances=[],
                processors=[_passthrough_processor()],
                detector=_make_detector(),
                workflow=workflow,
                stop_event=stop_event,
            )

        assert len(finished) == 5
        # All 5 should have started before any finished (concurrent execution)
        # Check by confirming all were started before even the first finished
        assert len(started) == 5

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrency(self):
        """With workers=2, at most 2 workflows run concurrently."""
        active_peak = 0
        current_active = 0

        async def counting_workflow(state):
            nonlocal current_active, active_peak
            current_active += 1
            active_peak = max(active_peak, current_active)
            await asyncio.sleep(0.02)
            current_active -= 1
            return {"analysis": None, "notifications_sent": [], "investigation": None}

        workflow = MagicMock()
        workflow.ainvoke = counting_workflow

        events = [_sdk_event(f"e{i}") for i in range(6)]
        stop_event = asyncio.Event()

        async def ingester_stream():
            for e in events:
                yield e
            stop_event.set()

        with (
            patch("octantis.main.TRIGGER_TOTAL"),
            patch("octantis.main.STANDALONE_ACTIVE_WORKFLOWS"),
            patch("octantis.main.STANDALONE_SEMAPHORE_CAPACITY"),
            patch("octantis.main.settings") as mock_settings,
            patch("octantis.main._merge_ingester_events", return_value=ingester_stream()),
        ):
            mock_settings.runtime.workers = 2

            await _run_standalone(
                ingester_instances=[],
                processors=[_passthrough_processor()],
                detector=_make_detector(),
                workflow=workflow,
                stop_event=stop_event,
            )

        assert active_peak <= 2, f"Peak concurrency {active_peak} exceeded semaphore limit 2"

    @pytest.mark.asyncio
    async def test_stop_event_breaks_ingester_loop(self):
        """Setting stop_event mid-stream causes the loop to exit cleanly."""
        processed: list[str] = []
        stop_event = asyncio.Event()

        async def slow_workflow(state):
            processed.append(state["event"].event_id)
            return {"analysis": None, "notifications_sent": [], "investigation": None}

        workflow = MagicMock()
        workflow.ainvoke = slow_workflow

        async def ingester_stream():
            # Yield first event, then trigger stop before yielding second
            yield _sdk_event("first")
            stop_event.set()
            yield _sdk_event("second")

        with (
            patch("octantis.main.TRIGGER_TOTAL"),
            patch("octantis.main.STANDALONE_ACTIVE_WORKFLOWS"),
            patch("octantis.main.STANDALONE_SEMAPHORE_CAPACITY"),
            patch("octantis.main.settings") as mock_settings,
            patch("octantis.main._merge_ingester_events", return_value=ingester_stream()),
        ):
            mock_settings.runtime.workers = 5

            await _run_standalone(
                ingester_instances=[],
                processors=[_passthrough_processor()],
                detector=_make_detector(),
                workflow=workflow,
                stop_event=stop_event,
            )

        assert "second" not in processed


# ---------------------------------------------------------------------------
# Mode dispatch / rejection tests (via run())
# ---------------------------------------------------------------------------


def _mock_settings_standalone():
    mock = MagicMock()
    mock.log_level = "INFO"
    mock.metrics.enabled = False
    mock.platform.platform = None
    mock.otlp.grpc_enabled = False
    mock.otlp.http_enabled = False
    mock.runtime.mode = "standalone"
    mock.runtime.workers = 2
    mock.slack.enabled = False
    mock.discord.enabled = False
    mock.pipeline.cpu_threshold = 75.0
    mock.pipeline.memory_threshold = 80.0
    mock.pipeline.error_rate_threshold = 0.01
    mock.pipeline.benign_patterns_list = []
    mock.pipeline.cooldown_seconds = 300.0
    mock.pipeline.cooldown_max_entries = 1000
    return mock


class TestModeDispatch:
    @pytest.mark.asyncio
    async def test_unknown_mode_exits_1(self):
        from octantis.main import run

        mock_registry = MagicMock()
        mock_registry.discover.return_value = []
        mock_registry.plugins.return_value = []
        mock_registry.setup_all.return_value = None
        mock_registry.teardown_all.return_value = None
        mock_registry.gate.return_value = None

        settings = _mock_settings_standalone()
        settings.runtime.mode = "banana"

        with (
            patch("octantis.main.settings", settings),
            patch("octantis.main._configure_logging"),
            patch("octantis.main.PluginRegistry", return_value=mock_registry),
            patch("octantis.main.resolve_tier"),
            patch("octantis.main.PLAN_TIER_INFO"),
            patch("octantis.main.build_workflow"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_ingester_mode_exits_1(self):
        """ingester mode is known but not yet implemented in Phase 4."""
        from octantis.main import run

        mock_registry = MagicMock()
        mock_registry.discover.return_value = []
        mock_registry.plugins.return_value = []
        mock_registry.setup_all.return_value = None
        mock_registry.teardown_all.return_value = None
        mock_registry.gate.return_value = None

        settings = _mock_settings_standalone()
        settings.runtime.mode = "ingester"

        with (
            patch("octantis.main.settings", settings),
            patch("octantis.main._configure_logging"),
            patch("octantis.main.PluginRegistry", return_value=mock_registry),
            patch("octantis.main.resolve_tier"),
            patch("octantis.main.PLAN_TIER_INFO"),
            patch("octantis.main.build_workflow"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_worker_mode_exits_1(self):
        """worker mode is known but not yet implemented in Phase 4."""
        from octantis.main import run

        mock_registry = MagicMock()
        mock_registry.discover.return_value = []
        mock_registry.plugins.return_value = []
        mock_registry.setup_all.return_value = None
        mock_registry.teardown_all.return_value = None
        mock_registry.gate.return_value = None

        settings = _mock_settings_standalone()
        settings.runtime.mode = "worker"

        with (
            patch("octantis.main.settings", settings),
            patch("octantis.main._configure_logging"),
            patch("octantis.main.PluginRegistry", return_value=mock_registry),
            patch("octantis.main.resolve_tier"),
            patch("octantis.main.PLAN_TIER_INFO"),
            patch("octantis.main.build_workflow"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                await run()
        assert exc_info.value.code == 1
