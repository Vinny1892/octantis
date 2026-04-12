"""Tests for built-in OTLP Receiver plugin adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octantis_plugin_sdk import Receiver

from octantis.plugins.builtins.receiver_plugin import OTLPReceiverPlugin


class TestOTLPReceiverPluginProtocol:
    def test_satisfies_protocol(self):
        plugin = OTLPReceiverPlugin()
        assert isinstance(plugin, Receiver)

    def test_setup_creates_receiver(self):
        with patch("octantis.plugins.builtins.receiver_plugin.settings"):
            plugin = OTLPReceiverPlugin()
            plugin.setup({})
        assert plugin._receiver is not None

    def test_teardown_clears_receiver(self):
        with patch("octantis.plugins.builtins.receiver_plugin.settings"):
            plugin = OTLPReceiverPlugin()
            plugin.setup({})
        plugin.teardown()
        assert plugin._receiver is None

    def test_receiver_property(self):
        with patch("octantis.plugins.builtins.receiver_plugin.settings"):
            plugin = OTLPReceiverPlugin()
            plugin.setup({})
        assert plugin.receiver is not None

    def test_receiver_property_none(self):
        plugin = OTLPReceiverPlugin()
        assert plugin.receiver is None


class TestOTLPReceiverPluginLifecycle:
    @pytest.mark.asyncio
    async def test_start_calls_receiver(self):
        plugin = OTLPReceiverPlugin()
        mock_receiver = MagicMock()
        mock_receiver.start = AsyncMock()
        plugin._receiver = mock_receiver

        await plugin.start()
        mock_receiver.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_skips_when_no_receiver(self):
        plugin = OTLPReceiverPlugin()
        await plugin.start()

    @pytest.mark.asyncio
    async def test_stop_calls_receiver(self):
        plugin = OTLPReceiverPlugin()
        mock_receiver = MagicMock()
        mock_receiver.stop = AsyncMock()
        plugin._receiver = mock_receiver

        await plugin.stop()
        mock_receiver.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_skips_when_no_receiver(self):
        plugin = OTLPReceiverPlugin()
        await plugin.stop()


class TestOTLPReceiverPluginEvents:
    @pytest.mark.asyncio
    async def test_events_yields_from_receiver(self):
        from octantis.models.event import InfraEvent

        event = InfraEvent(event_id="e1", event_type="metric", source="test")

        async def fake_events():
            yield event

        plugin = OTLPReceiverPlugin()
        mock_receiver = MagicMock()
        mock_receiver.events.return_value = fake_events()
        plugin._receiver = mock_receiver

        collected = []
        async for e in plugin.events():
            collected.append(e)

        assert len(collected) == 1
        assert collected[0].event_id == "e1"

    @pytest.mark.asyncio
    async def test_events_skips_when_no_receiver(self):
        plugin = OTLPReceiverPlugin()
        collected = []
        async for _ in plugin.events():
            collected.append(_)
        assert collected == []
