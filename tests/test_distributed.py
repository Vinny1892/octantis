"""Tests for the distributed runtime (Phase 5 — Redpanda ingester + worker).

Covers:
- producer: connects, serializes events, publishes to topic, metrics incremented
- producer: exponential backoff on connect failures, exits non-zero after max_attempts
- consumer: deserializes events, calls _process_one_event, commits offset on success
- consumer: does NOT commit on processing failure (redelivery), increments redelivered metric
- consumer: commits past permanently-corrupt messages to avoid stuck consumer
- consumer: stops cleanly when stop_event fires
- _sdk_event_to_dict / _dict_to_sdk_event round-trip
- config: RedpandaSettings defaults and env-prefix wiring
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octantis_plugin_sdk import Event as SDKEvent

from octantis.distributed.consumer import _dict_to_sdk_event
from octantis.distributed.producer import _backoff, _sdk_event_to_dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sdk_event(event_id: str = "evt-1") -> SDKEvent:
    return SDKEvent(
        event_id=event_id,
        event_type="metric",
        source="svc",
        resource={"service.name": "svc", "host.name": "node-1"},
        metrics=[{"name": "cpu", "value": 88.5}],
        logs=[],
    )


# ---------------------------------------------------------------------------
# Backoff helper
# ---------------------------------------------------------------------------


def test_backoff_base():
    assert _backoff(1) == 1.0  # 2^0 = 1
    assert _backoff(2) == 2.0  # 2^1 = 2
    assert _backoff(3) == 4.0
    assert _backoff(4) == 8.0


def test_backoff_cap():
    # Should never exceed 60
    assert _backoff(10) == 60.0
    assert _backoff(100) == 60.0


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_sdk_event_to_dict_round_trip():
    event = _make_sdk_event("round-trip-1")
    d = _sdk_event_to_dict(event)

    assert d["event_id"] == "round-trip-1"
    assert d["event_type"] == "metric"
    assert d["source"] == "svc"
    assert d["resource"]["service.name"] == "svc"
    assert d["metrics"][0]["name"] == "cpu"
    assert d["metrics"][0]["value"] == 88.5
    assert d["logs"] == []


def test_dict_to_sdk_event_round_trip():
    event = _make_sdk_event("round-trip-2")
    d = _sdk_event_to_dict(event)
    restored = _dict_to_sdk_event(d)

    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.source == event.source
    assert restored.resource == dict(event.resource)
    assert restored.metrics == list(event.metrics)


def test_dict_to_sdk_event_missing_optional_fields():
    d = {
        "event_id": "minimal",
        "event_type": "log",
        "source": "app",
        # resource, metrics, logs intentionally absent
    }
    event = _dict_to_sdk_event(d)
    assert event.event_id == "minimal"
    assert event.resource == {}
    assert event.metrics == []
    assert event.logs == []


# ---------------------------------------------------------------------------
# Producer tests
# ---------------------------------------------------------------------------


class TestProducer:
    @pytest.mark.asyncio
    async def test_publish_single_event(self):
        """Producer serializes and publishes an SDK Event to the topic."""
        event = _make_sdk_event("pub-1")
        stop_event = asyncio.Event()
        published_payloads: list = []

        mock_producer = AsyncMock()

        async def fake_send_and_wait(topic, value):
            published_payloads.append(value)

        mock_producer.send_and_wait = fake_send_and_wait
        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()

        async def fake_merge(ingesters, stop):
            yield event
            stop_event.set()

        with (
            patch("octantis.distributed.producer._create_producer", return_value=mock_producer),
            patch("octantis.distributed.producer._merge_ingester_events", side_effect=fake_merge),
            patch("octantis.distributed.producer.DISTRIBUTED_PUBLISHED") as mock_metric,
            patch("octantis.distributed.producer.settings") as mock_settings,
        ):
            mock_settings.redpanda.topic = "octantis.events"

            from octantis.distributed.producer import run_ingester

            await run_ingester(ingester_instances=[], stop_event=stop_event)

        assert len(published_payloads) == 1
        assert published_payloads[0]["event_id"] == "pub-1"
        mock_metric.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_error_logged_not_raised(self):
        """A KafkaError on publish is logged but does not propagate."""
        from aiokafka.errors import KafkaError

        event = _make_sdk_event("pub-err")
        stop_event = asyncio.Event()

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=KafkaError("broker down"))
        mock_producer.stop = AsyncMock()

        async def fake_merge(ingesters, stop):
            yield event
            stop_event.set()

        with (
            patch("octantis.distributed.producer._create_producer", return_value=mock_producer),
            patch("octantis.distributed.producer._merge_ingester_events", side_effect=fake_merge),
            patch("octantis.distributed.producer.DISTRIBUTED_PUBLISHED"),
            patch("octantis.distributed.producer.settings") as mock_settings,
        ):
            mock_settings.redpanda.topic = "octantis.events"

            from octantis.distributed.producer import run_ingester

            # Should not raise
            await run_ingester(ingester_instances=[], stop_event=stop_event)

    @pytest.mark.asyncio
    async def test_connect_retry_success_on_second_attempt(self):
        """Producer succeeds on the second connect attempt."""
        from aiokafka.errors import KafkaConnectionError

        attempt_count = 0
        mock_producer = AsyncMock()
        mock_producer.stop = AsyncMock()

        async def fake_start():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise KafkaConnectionError("refused")

        mock_producer.start = fake_start

        with (
            patch("octantis.distributed.producer.AIOKafkaProducer", return_value=mock_producer),
            patch("octantis.distributed.producer.asyncio.sleep", new_callable=AsyncMock),
            patch("octantis.distributed.producer.settings") as mock_settings,
        ):
            mock_settings.redpanda.brokers = "localhost:9092"
            mock_settings.redpanda.connect_max_attempts = 5

            from octantis.distributed.producer import _create_producer

            producer = await _create_producer()
            assert producer is mock_producer
            assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_connect_exhausted_exits_nonzero(self):
        """Producer exits with code 1 after all connect attempts fail."""
        from aiokafka.errors import KafkaConnectionError

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock(side_effect=KafkaConnectionError("refused"))
        mock_producer.stop = AsyncMock()

        with (
            patch("octantis.distributed.producer.AIOKafkaProducer", return_value=mock_producer),
            patch("octantis.distributed.producer.asyncio.sleep", new_callable=AsyncMock),
            patch("octantis.distributed.producer.settings") as mock_settings,
        ):
            mock_settings.redpanda.brokers = "localhost:9092"
            mock_settings.redpanda.connect_max_attempts = 3

            from octantis.distributed.producer import _create_producer

            with pytest.raises(SystemExit) as exc_info:
                await _create_producer()
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Consumer tests
# ---------------------------------------------------------------------------


def _make_kafka_message(event: SDKEvent, offset: int = 0):
    """Create a fake Kafka message dict-like object."""
    msg = MagicMock()
    msg.value = _sdk_event_to_dict(event)
    msg.offset = offset
    msg.partition = 0
    return msg


class TestConsumer:
    @pytest.mark.asyncio
    async def test_processes_and_commits_on_success(self):
        """Consumer calls _process_one_event and commits offset on success."""
        event = _make_sdk_event("cons-1")
        stop_event = asyncio.Event()
        msg = _make_kafka_message(event)

        processed = []
        committed = []

        async def fake_process(evt, processors, detector, workflow):
            processed.append(evt.event_id)

        mock_consumer = MagicMock()

        async def fake_iter():
            yield msg

        mock_consumer.__aiter__ = lambda self: fake_iter()
        mock_consumer.commit = AsyncMock(side_effect=lambda: committed.append(True))
        mock_consumer.stop = AsyncMock()
        mock_consumer.assignment = MagicMock(return_value=[])

        with (
            patch("octantis.distributed.consumer._create_consumer", return_value=mock_consumer),
            patch("octantis.distributed.consumer._process_one_event", side_effect=fake_process),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMED") as mock_consumed,
            patch("octantis.distributed.consumer.DISTRIBUTED_REDELIVERED"),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMER_LAG"),
            patch("octantis.distributed.consumer.settings") as mock_settings,
        ):
            mock_settings.redpanda.topic = "octantis.events"

            from octantis.distributed.consumer import run_worker

            await run_worker(
                processors=[],
                detector=MagicMock(),
                workflow=MagicMock(),
                stop_event=stop_event,
            )

        assert processed == ["cons-1"]
        assert len(committed) == 1
        mock_consumed.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_commit_on_processing_failure(self):
        """Consumer does NOT commit when _process_one_event raises."""
        event = _make_sdk_event("cons-fail")
        stop_event = asyncio.Event()
        msg = _make_kafka_message(event)

        committed = []

        async def failing_process(evt, processors, detector, workflow):
            raise RuntimeError("workflow exploded")

        mock_consumer = MagicMock()

        async def fake_iter():
            yield msg

        mock_consumer.__aiter__ = lambda self: fake_iter()
        mock_consumer.commit = AsyncMock(side_effect=lambda: committed.append(True))
        mock_consumer.stop = AsyncMock()
        mock_consumer.assignment = MagicMock(return_value=[])

        with (
            patch("octantis.distributed.consumer._create_consumer", return_value=mock_consumer),
            patch("octantis.distributed.consumer._process_one_event", side_effect=failing_process),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMED"),
            patch("octantis.distributed.consumer.DISTRIBUTED_REDELIVERED") as mock_redeliver,
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMER_LAG"),
            patch("octantis.distributed.consumer.settings") as mock_settings,
        ):
            mock_settings.redpanda.topic = "octantis.events"

            from octantis.distributed.consumer import run_worker

            await run_worker(
                processors=[],
                detector=MagicMock(),
                workflow=MagicMock(),
                stop_event=stop_event,
            )

        assert committed == [], "Offset must NOT be committed on failure"
        mock_redeliver.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_commits_past_corrupt_message(self):
        """A permanently-corrupt message (bad JSON schema) is committed to avoid a stuck consumer."""
        stop_event = asyncio.Event()
        msg = MagicMock()
        msg.value = {"broken": True}  # missing required keys
        msg.offset = 99
        msg.partition = 0

        committed = []

        mock_consumer = MagicMock()

        async def fake_iter():
            yield msg

        mock_consumer.__aiter__ = lambda self: fake_iter()
        mock_consumer.commit = AsyncMock(side_effect=lambda: committed.append(True))
        mock_consumer.stop = AsyncMock()
        mock_consumer.assignment = MagicMock(return_value=[])

        with (
            patch("octantis.distributed.consumer._create_consumer", return_value=mock_consumer),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMED"),
            patch("octantis.distributed.consumer.DISTRIBUTED_REDELIVERED"),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMER_LAG"),
            patch("octantis.distributed.consumer.settings") as mock_settings,
        ):
            mock_settings.redpanda.topic = "octantis.events"

            from octantis.distributed.consumer import run_worker

            await run_worker(
                processors=[],
                detector=MagicMock(),
                workflow=MagicMock(),
                stop_event=stop_event,
            )

        assert len(committed) == 1, "Corrupt message should be committed to skip it"

    @pytest.mark.asyncio
    async def test_stop_event_breaks_loop(self):
        """Setting stop_event causes the worker to exit cleanly."""
        event = _make_sdk_event("stop-test")
        stop_event = asyncio.Event()
        msg = _make_kafka_message(event)

        processed = []

        async def fake_process(evt, processors, detector, workflow):
            processed.append(evt.event_id)

        mock_consumer = MagicMock()

        async def fake_iter():
            yield msg
            stop_event.set()
            yield _make_kafka_message(_make_sdk_event("after-stop"))

        mock_consumer.__aiter__ = lambda self: fake_iter()
        mock_consumer.commit = AsyncMock()
        mock_consumer.stop = AsyncMock()
        mock_consumer.assignment = MagicMock(return_value=[])

        with (
            patch("octantis.distributed.consumer._create_consumer", return_value=mock_consumer),
            patch("octantis.distributed.consumer._process_one_event", side_effect=fake_process),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMED"),
            patch("octantis.distributed.consumer.DISTRIBUTED_REDELIVERED"),
            patch("octantis.distributed.consumer.DISTRIBUTED_CONSUMER_LAG"),
            patch("octantis.distributed.consumer.settings") as mock_settings,
        ):
            mock_settings.redpanda.topic = "octantis.events"

            from octantis.distributed.consumer import run_worker

            await run_worker(
                processors=[],
                detector=MagicMock(),
                workflow=MagicMock(),
                stop_event=stop_event,
            )

        assert "after-stop" not in processed

    @pytest.mark.asyncio
    async def test_consumer_connect_exhausted_exits_nonzero(self):
        """Consumer exits with code 1 after all connect attempts fail."""
        from aiokafka.errors import KafkaConnectionError

        mock_consumer = AsyncMock()
        mock_consumer.start = AsyncMock(side_effect=KafkaConnectionError("refused"))
        mock_consumer.stop = AsyncMock()

        with (
            patch("octantis.distributed.consumer.AIOKafkaConsumer", return_value=mock_consumer),
            patch("octantis.distributed.consumer.asyncio.sleep", new_callable=AsyncMock),
            patch("octantis.distributed.consumer.settings") as mock_settings,
        ):
            mock_settings.redpanda.brokers = "localhost:9092"
            mock_settings.redpanda.topic = "octantis.events"
            mock_settings.redpanda.consumer_group = "test-group"
            mock_settings.redpanda.connect_max_attempts = 3

            from octantis.distributed.consumer import _create_consumer

            with pytest.raises(SystemExit) as exc_info:
                await _create_consumer()
            assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_consumer_connect_retry_success(self):
        """Consumer succeeds on the second connect attempt."""
        from aiokafka.errors import KafkaConnectionError

        attempt_count = 0
        mock_consumer = AsyncMock()
        mock_consumer.stop = AsyncMock()

        async def fake_start():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise KafkaConnectionError("refused")

        mock_consumer.start = fake_start

        with (
            patch("octantis.distributed.consumer.AIOKafkaConsumer", return_value=mock_consumer),
            patch("octantis.distributed.consumer.asyncio.sleep", new_callable=AsyncMock),
            patch("octantis.distributed.consumer.settings") as mock_settings,
        ):
            mock_settings.redpanda.brokers = "localhost:9092"
            mock_settings.redpanda.topic = "octantis.events"
            mock_settings.redpanda.consumer_group = "test-group"
            mock_settings.redpanda.connect_max_attempts = 5

            from octantis.distributed.consumer import _create_consumer

            consumer = await _create_consumer()
            assert consumer is mock_consumer
            assert attempt_count == 2


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_redpanda_settings_defaults():
    from octantis.config import RedpandaSettings

    cfg = RedpandaSettings()
    assert cfg.brokers == "localhost:9092"
    assert cfg.topic == "octantis.events"
    assert cfg.consumer_group == "octantis-workers"
    assert cfg.connect_max_attempts == 10


def test_redpanda_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("OCTANTIS_REDPANDA_BROKERS", "broker1:9092,broker2:9092")
    monkeypatch.setenv("OCTANTIS_REDPANDA_TOPIC", "my.topic")
    monkeypatch.setenv("OCTANTIS_REDPANDA_CONSUMER_GROUP", "my-group")

    from octantis.config import RedpandaSettings

    cfg = RedpandaSettings()
    assert cfg.brokers == "broker1:9092,broker2:9092"
    assert cfg.topic == "my.topic"
    assert cfg.consumer_group == "my-group"
