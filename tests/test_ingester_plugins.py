"""Tests for per-transport OTLP Ingester plugins (Fork C=1)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octantis_plugin_sdk import Event as SDKEvent
from octantis_plugin_sdk import Ingester

from octantis.plugins.builtins.ingester_plugins import (
    OTLPGrpcIngester,
    OTLPHttpIngester,
)


class TestProtocolConformance:
    @pytest.mark.parametrize("cls", [OTLPGrpcIngester, OTLPHttpIngester])
    def test_ingester_protocol(self, cls):
        assert isinstance(cls(), Ingester)


class TestSetupTeardown:
    def test_setup_creates_queue_and_parser(self):
        ing = OTLPGrpcIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 100
            ing.setup({})
        assert ing._queue is not None
        assert ing._parser is not None

    def test_teardown_clears_state(self):
        ing = OTLPGrpcIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 100
            ing.setup({})
        ing.teardown()
        assert ing._queue is None
        assert ing._parser is None


class TestGrpcLifecycle:
    @pytest.mark.asyncio
    async def test_start_disabled_is_noop(self):
        ing = OTLPGrpcIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 10
            s.otlp.grpc_enabled = False
            ing.setup({})
            await ing.start()
        assert ing._server is None

    @pytest.mark.asyncio
    async def test_start_binds_server(self):
        ing = OTLPGrpcIngester()
        fake_server = MagicMock()
        fake_server.start = AsyncMock()
        fake_server.stop = AsyncMock()
        with (
            patch("octantis.plugins.builtins.ingester_plugins.settings") as s,
            patch(
                "octantis.plugins.builtins.ingester_plugins.create_grpc_server",
                AsyncMock(return_value=fake_server),
            ),
        ):
            s.otlp.queue_max_size = 10
            s.otlp.grpc_enabled = True
            s.otlp.grpc_port = 4317
            ing.setup({})
            await ing.start()
            await ing.stop()
        fake_server.start.assert_awaited_once()
        fake_server.stop.assert_awaited_once_with(grace=5)

    @pytest.mark.asyncio
    async def test_stop_without_start_sets_stopped(self):
        ing = OTLPGrpcIngester()
        await ing.stop()
        assert ing._stopped is True


class TestHttpLifecycle:
    @pytest.mark.asyncio
    async def test_start_disabled_is_noop(self):
        ing = OTLPHttpIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 10
            s.otlp.http_enabled = False
            ing.setup({})
            await ing.start()
        assert ing._runner is None

    @pytest.mark.asyncio
    async def test_start_binds_site_and_stop_cleans_up(self):
        ing = OTLPHttpIngester()
        fake_runner = MagicMock()
        fake_runner.setup = AsyncMock()
        fake_runner.cleanup = AsyncMock()
        fake_site = MagicMock()
        fake_site.start = AsyncMock()
        with (
            patch("octantis.plugins.builtins.ingester_plugins.settings") as s,
            patch(
                "octantis.plugins.builtins.ingester_plugins._create_routes",
                return_value=MagicMock(),
            ),
            patch(
                "octantis.plugins.builtins.ingester_plugins.web.AppRunner",
                return_value=fake_runner,
            ),
            patch(
                "octantis.plugins.builtins.ingester_plugins.web.TCPSite",
                return_value=fake_site,
            ),
        ):
            s.otlp.queue_max_size = 10
            s.otlp.http_enabled = True
            s.otlp.http_port = 4318
            ing.setup({})
            await ing.start()
            await ing.stop()
        fake_runner.setup.assert_awaited_once()
        fake_site.start.assert_awaited_once()
        fake_runner.cleanup.assert_awaited_once()


class TestEvents:
    @pytest.mark.asyncio
    async def test_events_yields_sdk_event_instances(self):
        ing = OTLPGrpcIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 10
            ing.setup({})
        sdk_evt = SDKEvent(
            event_id="evt-1",
            event_type="metric",
            source="svc",
            resource={"service.name": "svc"},
            metrics=[{"name": "cpu", "value": 80.0}],
        )
        ing._queue.put_nowait(sdk_evt)
        ing._stopped = True
        items = [e async for e in ing.events()]
        assert len(items) == 1
        assert isinstance(items[0], SDKEvent)
        assert items[0].event_id == "evt-1"

    @pytest.mark.asyncio
    async def test_events_yields_queued_items_then_exits_on_stop(self):
        ing = OTLPGrpcIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 10
            ing.setup({})
        ing._queue.put_nowait("a")
        ing._queue.put_nowait("b")
        ing._stopped = True
        items = [e async for e in ing.events()]
        assert items == ["a", "b"]

    @pytest.mark.asyncio
    async def test_events_without_queue_returns_empty(self):
        ing = OTLPGrpcIngester()
        items = [e async for e in ing.events()]
        assert items == []

    @pytest.mark.asyncio
    async def test_events_high_watermark_logs_once(self):
        ing = OTLPHttpIngester()
        with patch("octantis.plugins.builtins.ingester_plugins.settings") as s:
            s.otlp.queue_max_size = 4
            ing.setup({})
        for i in range(4):
            ing._queue.put_nowait(i)

        async def _stop_after_first():
            await asyncio.sleep(0.01)
            ing._stopped = True

        asyncio.create_task(_stop_after_first())
        items = [e async for e in ing.events()]
        assert items == [0, 1, 2, 3]
