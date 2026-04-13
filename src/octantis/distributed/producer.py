# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingester-mode runner: fan-in Ingester plugins → Redpanda topic.

Each SDK Event is serialized as UTF-8 JSON and produced to the configured
Kafka/Redpanda topic. The producer retries connection with exponential backoff
(2s → 4s → 8s → … → 60s cap) and exits non-zero after connect_max_attempts.
"""

import asyncio
import json
import sys

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError, KafkaError

from octantis.config import settings
from octantis.main import _merge_ingester_events
from octantis.metrics import DISTRIBUTED_PUBLISHED

log = structlog.get_logger(__name__)

_BACKOFF_BASE: float = 2.0
_BACKOFF_CAP: float = 60.0


def _backoff(attempt: int) -> float:
    """Exponential backoff: 2^(attempt-1) seconds, capped at 60."""
    return min(_BACKOFF_BASE ** (attempt - 1), _BACKOFF_CAP)


async def _create_producer() -> AIOKafkaProducer:
    """Connect to Redpanda with exponential backoff retry.

    Raises SystemExit(1) if all attempts are exhausted.
    """
    cfg = settings.redpanda
    max_attempts = cfg.connect_max_attempts

    for attempt in range(1, max_attempts + 1):
        producer = AIOKafkaProducer(
            bootstrap_servers=cfg.brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        try:
            await producer.start()
            log.info(
                "octantis.ingester.producer_connected",
                brokers=cfg.brokers,
                attempt=attempt,
            )
            return producer
        except (KafkaConnectionError, KafkaError, OSError) as exc:
            await producer.stop()
            delay = _backoff(attempt)
            log.warning(
                "octantis.ingester.producer_connect_failed",
                attempt=attempt,
                max_attempts=max_attempts,
                delay_s=delay,
                error=str(exc),
            )
            if attempt == max_attempts:
                log.error(
                    "octantis.ingester.producer_connect_exhausted",
                    max_attempts=max_attempts,
                    brokers=cfg.brokers,
                )
                sys.exit(1)
            await asyncio.sleep(delay)

    # unreachable — sys.exit above fires first
    raise RuntimeError("unreachable")  # pragma: no cover


def _sdk_event_to_dict(event) -> dict:
    """Serialize an SDK Event to a plain dict suitable for JSON encoding."""
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "source": event.source,
        "resource": dict(event.resource),
        "metrics": list(event.metrics),
        "logs": list(event.logs),
        "raw_payload": event.raw_payload,
    }


async def run_ingester(
    ingester_instances: list,
    stop_event: asyncio.Event,
) -> None:
    """Ingest events from all Ingester plugins and publish to Redpanda.

    This is the entry point for ``OCTANTIS_MODE=ingester``. It:
    1. Connects a Kafka producer (with retry).
    2. Fan-in merges all registered Ingester.events() streams.
    3. Serializes each SDK Event to JSON and produces to the configured topic.
    4. Commits (flush) are implicit — aiokafka batches and acks automatically.
    5. Stops cleanly when stop_event fires.
    """
    topic = settings.redpanda.topic
    producer = await _create_producer()

    log.info("octantis.ingester.started", topic=topic)

    try:
        async for event in _merge_ingester_events(ingester_instances, stop_event):
            if stop_event.is_set():
                break
            payload = _sdk_event_to_dict(event)
            try:
                await producer.send_and_wait(topic, value=payload)
                DISTRIBUTED_PUBLISHED.inc()
                log.debug(
                    "octantis.ingester.published",
                    event_id=event.event_id,
                    topic=topic,
                )
            except KafkaError as exc:
                log.error(
                    "octantis.ingester.publish_failed",
                    event_id=event.event_id,
                    error=str(exc),
                )
    finally:
        await producer.stop()
        log.info("octantis.ingester.stopped")
