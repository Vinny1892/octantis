"""Batcher: groups events by (namespace, source) within a time window.

Instead of sending every event to the LLM individually, the batcher
accumulates events for the same workload and flushes them as a single
merged InfraEvent after `window_seconds` or when `max_batch_size` is hit.
This drastically reduces LLM calls for noisy sources.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from octantis.models.event import InfraEvent, OTelResource

log = structlog.get_logger(__name__)


def _batch_key(event: InfraEvent) -> str:
    """Stable key grouping events by workload identity."""
    ns = event.resource.k8s_namespace or "global"
    workload = (
        event.resource.k8s_deployment_name
        or event.resource.k8s_pod_name
        or event.resource.service_name
        or event.source
    )
    return f"{ns}/{workload}"


def _merge_events(events: list[InfraEvent]) -> InfraEvent:
    """Merge a batch of events into one representative InfraEvent."""
    if not events:
        raise ValueError("Cannot merge empty batch")
    if len(events) == 1:
        return events[0]

    base = events[0]
    merged_metrics = []
    merged_logs = []
    merged_raw: dict = {"_batch_size": len(events), "_event_ids": []}

    seen_metrics: set[str] = set()
    for e in events:
        merged_raw["_event_ids"].append(e.event_id)
        for m in e.metrics:
            # Keep most recent value per metric name
            if m.name not in seen_metrics:
                merged_metrics.append(m)
                seen_metrics.add(m.name)
            else:
                # Replace with newer value (events are appended chronologically)
                for i, existing in enumerate(merged_metrics):
                    if existing.name == m.name:
                        merged_metrics[i] = m
                        break
        merged_logs.extend(e.logs)

    # Keep only the last N logs to avoid oversized prompts
    merged_logs = merged_logs[-20:]

    return InfraEvent(
        event_id=f"batch-{uuid.uuid4().hex[:8]}",
        event_type=base.event_type,
        source=base.source,
        resource=base.resource,
        metrics=merged_metrics,
        logs=merged_logs,
        raw_payload=merged_raw,
        received_at=datetime.utcnow(),
    )


@dataclass
class _Bucket:
    events: list[InfraEvent] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


class EventBatcher:
    """Accumulates events per workload key and flushes batches on timeout or size limit.

    Usage:
        batcher = EventBatcher(window_seconds=30, max_batch_size=20)
        async for batch in batcher.run(event_stream):
            await workflow.ainvoke({"event": batch})
    """

    def __init__(self, window_seconds: float = 30.0, max_batch_size: int = 20) -> None:
        self._window = window_seconds
        self._max_size = max_batch_size
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self._flush_queue: asyncio.Queue[InfraEvent] = asyncio.Queue()
        self._flush_task: asyncio.Task | None = None

    async def _periodic_flush(self) -> None:
        """Background task: flush stale buckets every second."""
        while True:
            await asyncio.sleep(1.0)
            now = asyncio.get_event_loop().time()
            keys_to_flush = [
                key
                for key, bucket in self._buckets.items()
                if (now - bucket.created_at) >= self._window
            ]
            for key in keys_to_flush:
                await self._flush(key)

    async def _flush(self, key: str) -> None:
        bucket = self._buckets.pop(key, None)
        if not bucket or not bucket.events:
            return
        merged = _merge_events(bucket.events)
        log.info(
            "batcher.flush",
            key=key,
            batch_size=len(bucket.events),
            merged_event_id=merged.event_id,
        )
        await self._flush_queue.put(merged)

    async def add(self, event: InfraEvent) -> None:
        """Add an event to its bucket, flushing immediately if max size is hit."""
        key = _batch_key(event)
        if key not in self._buckets:
            self._buckets[key] = _Bucket()
        self._buckets[key].events.append(event)

        if len(self._buckets[key].events) >= self._max_size:
            log.debug("batcher.max_size_reached", key=key, size=self._max_size)
            await self._flush(key)

    async def run(self, source: "AsyncIterator[InfraEvent]") -> "AsyncIterator[InfraEvent]":
        """Wrap an async event iterator with batching.

        Yields merged InfraEvent objects ready for the LLM pipeline.
        """
        self._flush_task = asyncio.create_task(self._periodic_flush())
        try:
            async for event in source:
                await self.add(event)
                # Drain any ready batches
                while not self._flush_queue.empty():
                    yield await self._flush_queue.get()
        finally:
            # Flush remaining buckets on shutdown
            for key in list(self._buckets.keys()):
                await self._flush(key)
            while not self._flush_queue.empty():
                yield await self._flush_queue.get()
            self._flush_task.cancel()
