# SPDX-License-Identifier: AGPL-3.0-or-later
"""Worker-mode runner: Redpanda topic → processor chain → LangGraph workflow.

Consumes SDK Events from the configured Kafka/Redpanda topic, deserializes them,
runs the full processor → environment-detect → workflow pipeline, and commits the
offset **only** on successful completion (at-least-once delivery).

Exponential backoff (2s → 4s → … → 60s cap) is used for the initial consumer
connection. Offset commits are per-message after successful processing.
"""

import asyncio
import json
import sys
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError, KafkaError
from octantis_plugin_sdk import Event as SDKEvent

from octantis.config import settings
from octantis.main import _process_one_event
from octantis.metrics import (
    DISTRIBUTED_CONSUMED,
    DISTRIBUTED_CONSUMER_LAG,
    DISTRIBUTED_REDELIVERED,
)

log = structlog.get_logger(__name__)

_BACKOFF_BASE: float = 2.0
_BACKOFF_CAP: float = 60.0


def _backoff(attempt: int) -> float:
    return min(_BACKOFF_BASE ** (attempt - 1), _BACKOFF_CAP)


async def _create_consumer() -> AIOKafkaConsumer:
    """Connect to Redpanda with exponential backoff retry.

    Raises SystemExit(1) if all attempts are exhausted.
    """
    cfg = settings.redpanda
    max_attempts = cfg.connect_max_attempts

    for attempt in range(1, max_attempts + 1):
        consumer = AIOKafkaConsumer(
            cfg.topic,
            bootstrap_servers=cfg.brokers,
            group_id=cfg.consumer_group,
            enable_auto_commit=False,  # manual commit after successful processing
            auto_offset_reset="earliest",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        try:
            await consumer.start()
            log.info(
                "octantis.worker.consumer_connected",
                brokers=cfg.brokers,
                topic=cfg.topic,
                group=cfg.consumer_group,
                attempt=attempt,
            )
            return consumer
        except (KafkaConnectionError, KafkaError, OSError) as exc:
            await consumer.stop()
            delay = _backoff(attempt)
            log.warning(
                "octantis.worker.consumer_connect_failed",
                attempt=attempt,
                max_attempts=max_attempts,
                delay_s=delay,
                error=str(exc),
            )
            if attempt == max_attempts:
                log.error(
                    "octantis.worker.consumer_connect_exhausted",
                    max_attempts=max_attempts,
                    brokers=cfg.brokers,
                )
                sys.exit(1)
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")  # pragma: no cover


def _dict_to_sdk_event(data: dict) -> SDKEvent:
    """Deserialize a plain dict (from Kafka) back to an SDK Event."""
    return SDKEvent(
        event_id=data["event_id"],
        event_type=data["event_type"],
        source=data["source"],
        resource=data.get("resource", {}),
        metrics=data.get("metrics", []),
        logs=data.get("logs", []),
        raw_payload=data.get("raw_payload") or {},
    )


async def run_worker(
    processors: list,
    detector: Any,
    workflow: Any,
    stop_event: asyncio.Event,
) -> None:
    """Consume events from Redpanda and run the investigation pipeline.

    This is the entry point for ``OCTANTIS_MODE=worker``. It:
    1. Connects a Kafka consumer (with retry).
    2. Polls messages in a loop until stop_event fires.
    3. Deserializes the JSON payload back to an SDK Event.
    4. Runs _process_one_event (processors → detect → workflow).
    5. Commits the offset only after successful processing (at-least-once).
    6. On processing error, logs the error but does NOT commit — the message
       will be redelivered after consumer restart or rebalance.
    """
    consumer = await _create_consumer()
    log.info("octantis.worker.started", topic=settings.redpanda.topic)

    try:
        async for msg in consumer:
            if stop_event.is_set():
                break

            try:
                data = msg.value
                event = _dict_to_sdk_event(data)
            except (KeyError, TypeError, ValueError) as exc:
                log.error(
                    "octantis.worker.deserialize_failed",
                    offset=msg.offset,
                    partition=msg.partition,
                    error=str(exc),
                )
                # Commit past a permanently-corrupt message to avoid stuck consumer
                await consumer.commit()
                continue

            # Track consumer lag metric
            try:
                partitions = consumer.assignment()
                for tp in partitions:
                    end_offsets = await consumer.end_offsets([tp])
                    lag = end_offsets[tp] - consumer.highwater(tp)
                    DISTRIBUTED_CONSUMER_LAG.set(max(0, lag))
            except Exception:
                pass  # lag metric is best-effort

            try:
                await _process_one_event(event, processors, detector, workflow)
                await consumer.commit()
                DISTRIBUTED_CONSUMED.inc()
                log.debug(
                    "octantis.worker.processed",
                    event_id=event.event_id,
                    offset=msg.offset,
                )
            except Exception as exc:
                # Do NOT commit — message will be redelivered
                DISTRIBUTED_REDELIVERED.inc()
                log.error(
                    "octantis.worker.processing_failed",
                    event_id=getattr(event, "event_id", "?"),
                    offset=msg.offset,
                    error=str(exc),
                    exc_info=True,
                )
    finally:
        await consumer.stop()
        log.info("octantis.worker.stopped")
