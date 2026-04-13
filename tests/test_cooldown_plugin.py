"""Tests for the fingerprint-cooldown built-in plugin adapter."""

from __future__ import annotations

import asyncio

from octantis_plugin_sdk import Event, Processor

from octantis.plugins.builtins.cooldown_plugin import FingerprintCooldownPlugin


def _event(event_id: str = "e1") -> Event:
    return Event(
        event_id=event_id,
        event_type="metric",
        source="svc-a",
        resource={"k8s.namespace.name": "prod", "k8s.deployment.name": "api"},
    )


def test_plugin_satisfies_processor_protocol():
    assert isinstance(FingerprintCooldownPlugin(), Processor)


def test_name_and_priority():
    p = FingerprintCooldownPlugin()
    assert p.name == "fingerprint-cooldown"
    assert p.priority == 200


def test_process_before_setup_passes_through():
    p = FingerprintCooldownPlugin()
    evt = _event()
    assert asyncio.run(p.process(evt)) is evt


def test_first_occurrence_passes_second_suppressed():
    p = FingerprintCooldownPlugin()
    p.setup({"cooldown_seconds": 300, "max_entries": 10})
    evt = _event()
    assert asyncio.run(p.process(evt)) is evt  # first seen → pass
    assert asyncio.run(p.process(evt)) is None  # within window → drop
    p.teardown()


def test_different_fingerprints_both_pass():
    p = FingerprintCooldownPlugin()
    p.setup({})
    e1 = Event(
        event_id="e1", event_type="metric", source="svc-a", resource={"k8s.deployment.name": "api"}
    )
    e2 = Event(
        event_id="e2",
        event_type="metric",
        source="svc-b",
        resource={"k8s.deployment.name": "worker"},
    )
    assert asyncio.run(p.process(e1)) is e1
    assert asyncio.run(p.process(e2)) is e2
    p.teardown()


def test_stats_before_and_after_setup():
    p = FingerprintCooldownPlugin()
    pre = p.stats()
    assert pre["tracked_fingerprints"] == 0
    p.setup({"cooldown_seconds": 10, "max_entries": 5})
    asyncio.run(p.process(_event()))
    stats = p.stats()
    assert stats["tracked_fingerprints"] == 1
    assert stats["cooldown_seconds"] == 10
    assert stats["max_entries"] == 5
    p.teardown()
    assert p.stats()["tracked_fingerprints"] == 0


def test_teardown_resets_internal_state():
    p = FingerprintCooldownPlugin()
    p.setup({})
    asyncio.run(p.process(_event()))
    p.teardown()
    # After teardown, cooldown is cleared; same event passes again
    p.setup({})
    assert asyncio.run(p.process(_event())) is not None
    p.teardown()
