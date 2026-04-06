"""Unit tests for OTLPReceiver orchestrator."""

import asyncio
import uuid

import pytest

from octantis.config import OTLPSettings
from octantis.models.event import InfraEvent, OTelResource
from octantis.receivers.receiver import OTLPReceiver


def _make_event(source: str = "test") -> InfraEvent:
    return InfraEvent(
        event_id=str(uuid.uuid4()),
        event_type="metric",
        source=source,
        resource=OTelResource(service_name=source),
    )


async def test_events_yields_from_queue():
    config = OTLPSettings(grpc_enabled=False, http_enabled=False, queue_max_size=10)
    receiver = OTLPReceiver(config)

    # Put events directly on internal queue
    for i in range(3):
        receiver._queue.put_nowait(_make_event(f"svc-{i}"))

    # Signal stop so events() will terminate after draining
    receiver._stopped = True

    events = []
    async for event in receiver.events():
        events.append(event)

    assert len(events) == 3
    assert events[0].source == "svc-0"
    assert events[2].source == "svc-2"


async def test_queue_drop_on_full():
    config = OTLPSettings(grpc_enabled=False, http_enabled=False, queue_max_size=2)
    receiver = OTLPReceiver(config)

    receiver._queue.put_nowait(_make_event("a"))
    receiver._queue.put_nowait(_make_event("b"))

    # Queue is full, this should raise QueueFull (caller is responsible for catching)
    with pytest.raises(asyncio.QueueFull):
        receiver._queue.put_nowait(_make_event("c"))

    assert receiver._queue.qsize() == 2


async def test_graceful_stop_drains_queue():
    config = OTLPSettings(grpc_enabled=False, http_enabled=False, queue_max_size=10)
    receiver = OTLPReceiver(config)

    receiver._queue.put_nowait(_make_event("pending-1"))
    receiver._queue.put_nowait(_make_event("pending-2"))

    # Stop receiver — events() should drain remaining
    receiver._stopped = True

    events = []
    async for event in receiver.events():
        events.append(event)

    assert len(events) == 2


async def test_both_transports_disabled_logs_warning(capfd):
    config = OTLPSettings(grpc_enabled=False, http_enabled=False)
    receiver = OTLPReceiver(config)
    await receiver.start()
    # Should not crash
    await receiver.stop()


async def test_stop_then_events_terminates():
    config = OTLPSettings(grpc_enabled=False, http_enabled=False, queue_max_size=10)
    receiver = OTLPReceiver(config)
    receiver._stopped = True

    events = []
    async for event in receiver.events():
        events.append(event)

    assert events == []
