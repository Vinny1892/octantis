"""Tests for the trigger-filter built-in plugin adapter."""

from __future__ import annotations

import pytest
from octantis_plugin_sdk import Event, Processor

from octantis.plugins.builtins.trigger_filter_plugin import TriggerFilterPlugin


def _event() -> Event:
    return Event(event_id="e1", event_type="metric", source="test")


def test_plugin_satisfies_processor_protocol():
    assert isinstance(TriggerFilterPlugin(), Processor)


def test_plugin_name_and_priority():
    p = TriggerFilterPlugin()
    assert p.name == "trigger-filter"
    assert p.priority == 100


def test_process_before_setup_returns_event_unchanged():
    p = TriggerFilterPlugin()
    evt = _event()
    import asyncio
    result = asyncio.run(p.process(evt))
    assert result is evt


def test_setup_accepts_config_and_teardown_clears():
    p = TriggerFilterPlugin()
    p.setup({"cpu_threshold": 50.0, "memory_threshold": 60.0, "error_rate_threshold": 0.1})
    assert p._filter is not None
    p.teardown()
    assert p._filter is None


def test_process_drops_event_with_no_signal():
    """An event with no metrics and no logs should be dropped (NoSignalRule)."""
    p = TriggerFilterPlugin()
    p.setup({})
    import asyncio
    result = asyncio.run(p.process(_event()))
    assert result is None
    p.teardown()


def test_setup_with_empty_config_uses_defaults():
    p = TriggerFilterPlugin()
    p.setup({})
    assert p._filter is not None
    p.teardown()


def test_setup_with_benign_patterns():
    p = TriggerFilterPlugin()
    p.setup({"benign_patterns": ["healthz"]})
    assert p._filter is not None
    p.teardown()


@pytest.mark.asyncio
async def test_process_is_async():
    """process() must be awaitable per the Processor Protocol."""
    p = TriggerFilterPlugin()
    p.setup({})
    result = await p.process(_event())
    assert result is None or isinstance(result, Event)
    p.teardown()
