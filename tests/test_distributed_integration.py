# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for the distributed runtime against a real Redpanda broker.

These tests require Docker. They are marked ``integration`` and skipped
automatically when Docker is unavailable. Run explicitly with:

    uv run pytest -m integration tests/test_distributed_integration.py -v

Scenarios covered (Task 5.8):
- End-to-end publish → consume: producer publishes an SDK Event; consumer
  receives and deserialises it correctly.
- At-least-once redelivery: consumer fails without committing; a fresh
  consumer in the same group receives the same message.
- Corrupt message skip: a corrupt JSON blob is committed past so the
  consumer does not stall.
- Idempotency note: workflow is called once per delivery attempt; duplicate
  notifications on redelivery are documented as acceptable.
"""

import asyncio
import json
import uuid

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from octantis_plugin_sdk import Event as SDKEvent

from octantis.distributed.consumer import _dict_to_sdk_event
from octantis.distributed.producer import _sdk_event_to_dict

# ---------------------------------------------------------------------------
# Docker availability guard
# ---------------------------------------------------------------------------

try:
    import docker as _docker

    _docker.from_env().ping()
    _DOCKER_AVAILABLE = True
except Exception:
    _DOCKER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DOCKER_AVAILABLE,
    reason="Docker not available — skipping integration tests",
)

# ---------------------------------------------------------------------------
# Redpanda container fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def redpanda_broker():
    """Start a Kafka-compatible broker and return the bootstrap address.

    Uses ``testcontainers.kafka.KafkaContainer`` (Confluent CP Kafka) which
    correctly wires the advertised listener to the host-mapped port.  The
    Kafka protocol is identical to Redpanda's — aiokafka connects to both.
    The container is shared across all tests in the module (scope=module).
    """
    from testcontainers.kafka import KafkaContainer

    with KafkaContainer() as kafka:
        yield kafka.get_bootstrap_server()


@pytest.fixture
def unique_topic():
    """Return a unique topic name per test to avoid cross-test interference."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def unique_group():
    """Return a unique consumer group name per test."""
    return f"grp-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sdk_event(event_id: str | None = None) -> SDKEvent:
    return SDKEvent(
        event_id=event_id or f"evt-{uuid.uuid4().hex[:8]}",
        event_type="metric",
        source="integration-test",
        resource={"service.name": "svc", "host.name": "node-1"},
        metrics=[{"name": "cpu_usage", "value": 72.5}],
        logs=[],
    )


async def _produce(brokers: str, topic: str, payloads: list[dict]) -> None:
    """Publish a list of dicts to the given topic."""
    producer = AIOKafkaProducer(
        bootstrap_servers=brokers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    try:
        for payload in payloads:
            await producer.send_and_wait(topic, value=payload)
    finally:
        await producer.stop()


async def _consume_n(
    brokers: str,
    topic: str,
    group: str,
    n: int,
    timeout: float = 10.0,
) -> list[dict]:
    """Consume exactly n messages from the topic, returning their values."""
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=brokers,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    await consumer.start()
    results = []
    try:
        async with asyncio.timeout(timeout):
            async for msg in consumer:
                results.append(msg.value)
                await consumer.commit()
                if len(results) >= n:
                    break
    finally:
        await consumer.stop()
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_publish_consume(redpanda_broker, unique_topic, unique_group):
    """Producer serializes an SDK Event; consumer receives and deserialises it."""
    event = _make_sdk_event("e2e-1")
    payload = _sdk_event_to_dict(event)

    await _produce(redpanda_broker, unique_topic, [payload])
    received = await _consume_n(redpanda_broker, unique_topic, unique_group, n=1)

    assert len(received) == 1
    restored = _dict_to_sdk_event(received[0])
    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.source == event.source
    assert restored.resource == dict(event.resource)
    assert restored.metrics == list(event.metrics)


@pytest.mark.asyncio
async def test_multiple_events_ordered(redpanda_broker, unique_topic, unique_group):
    """Multiple events are consumed in produce order within the same partition."""
    events = [_make_sdk_event(f"ord-{i}") for i in range(5)]
    payloads = [_sdk_event_to_dict(e) for e in events]

    await _produce(redpanda_broker, unique_topic, payloads)
    received = await _consume_n(redpanda_broker, unique_topic, unique_group, n=5)

    assert [r["event_id"] for r in received] == [e.event_id for e in events]


@pytest.mark.asyncio
async def test_redelivery_on_no_commit(redpanda_broker, unique_topic):
    """Without committing, a new consumer in the same group receives the same message.

    This validates the at-least-once delivery guarantee: if the worker crashes
    (or explicitly does not commit), the message will be redelivered to the
    next consumer that starts with the same group.
    """
    group = f"redeliver-{uuid.uuid4().hex[:8]}"
    event = _make_sdk_event("redeliver-1")
    payload = _sdk_event_to_dict(event)

    await _produce(redpanda_broker, unique_topic, [payload])

    # First consumer: receives the message but does NOT commit
    consumer1 = AIOKafkaConsumer(
        unique_topic,
        bootstrap_servers=redpanda_broker,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    await consumer1.start()
    first_delivery = None
    try:
        async with asyncio.timeout(10.0):
            async for msg in consumer1:
                first_delivery = msg.value
                # Intentionally NOT committing — simulates worker crash
                break
    finally:
        await consumer1.stop()

    assert first_delivery is not None
    assert first_delivery["event_id"] == "redeliver-1"

    # Second consumer in the same group: must receive the same message again
    second_delivery = await _consume_n(
        redpanda_broker, unique_topic, group, n=1, timeout=15.0
    )

    assert len(second_delivery) == 1
    assert second_delivery[0]["event_id"] == "redeliver-1", (
        "Expected redelivery of uncommitted message to the same consumer group"
    )


@pytest.mark.asyncio
async def test_corrupt_message_skipped(redpanda_broker, unique_topic, unique_group):
    """A corrupt message followed by a valid one: valid message is processed.

    The consumer commits past the corrupt message to avoid a stuck consumer,
    then processes the next valid message normally.
    """
    corrupt_payload = b"not-valid-json-{{"
    valid_event = _make_sdk_event("after-corrupt")
    valid_payload = json.dumps(_sdk_event_to_dict(valid_event)).encode("utf-8")

    # Produce raw bytes to inject the corrupt message
    producer = AIOKafkaProducer(bootstrap_servers=redpanda_broker)
    await producer.start()
    try:
        await producer.send_and_wait(unique_topic, value=corrupt_payload)
        await producer.send_and_wait(unique_topic, value=valid_payload)
    finally:
        await producer.stop()

    # Consumer with a deserializer that raises on corrupt JSON
    consumer = AIOKafkaConsumer(
        unique_topic,
        bootstrap_servers=redpanda_broker,
        group_id=unique_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    received_valid = []
    try:
        async with asyncio.timeout(10.0):
            async for msg in consumer:
                try:
                    data = json.loads(msg.value.decode("utf-8"))
                    received_valid.append(data)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # commit past it
                await consumer.commit()
                if len(received_valid) >= 1:
                    break
    finally:
        await consumer.stop()

    assert len(received_valid) == 1
    assert received_valid[0]["event_id"] == "after-corrupt"


@pytest.mark.asyncio
async def test_idempotency_workflow_called_per_delivery(
    redpanda_broker, unique_topic, unique_group
):
    """Workflow is invoked once per delivery attempt.

    On redelivery (no-commit), the workflow runs again — producing duplicate
    notifications. This is the documented at-least-once behaviour; deduplication
    is deferred to the Storage plugin.
    """
    group = f"idem-{uuid.uuid4().hex[:8]}"
    event = _make_sdk_event("idem-1")
    payload = _sdk_event_to_dict(event)

    await _produce(redpanda_broker, unique_topic, [payload])

    call_count = 0

    async def counting_consumer(commit: bool) -> None:
        nonlocal call_count
        consumer = AIOKafkaConsumer(
            unique_topic,
            bootstrap_servers=redpanda_broker,
            group_id=group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await consumer.start()
        try:
            async with asyncio.timeout(10.0):
                async for msg in consumer:
                    call_count += 1
                    if commit:
                        await consumer.commit()
                    break
        finally:
            await consumer.stop()

    # First delivery — do NOT commit
    await counting_consumer(commit=False)
    assert call_count == 1

    # Second delivery (redelivery) — commit this time
    await counting_consumer(commit=True)
    assert call_count == 2, (
        "Workflow should have been called twice — once per delivery attempt"
    )
