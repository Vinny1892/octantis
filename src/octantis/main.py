"""Octantis main entrypoint."""

import asyncio
import signal
import sys

import structlog

from octantis.config import settings
from octantis.consumers.redpanda import RedpandaConsumer
from octantis.graph.workflow import build_workflow
from octantis.pipeline import EventBatcher, PreFilter, Sampler

log = structlog.get_logger(__name__)


def _configure_logging() -> None:
    import logging

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def _build_pipeline():
    """Instantiate pre-filter, batcher, and sampler from settings."""
    cfg = settings.pipeline

    pre_filter = PreFilter.default(
        cpu_threshold=cfg.cpu_threshold,
        memory_threshold=cfg.memory_threshold,
        error_rate_threshold=cfg.error_rate_threshold,
        benign_patterns=cfg.benign_patterns_list,
        allowed_event_types=cfg.allowed_event_types_list,
    )
    batcher = EventBatcher(
        window_seconds=cfg.batch_window_seconds,
        max_batch_size=cfg.batch_max_size,
    )
    sampler = Sampler(
        cooldown_seconds=cfg.sampler_cooldown_seconds,
        max_entries=cfg.sampler_max_entries,
    )
    return pre_filter, batcher, sampler


async def run() -> None:
    """Main async run loop."""
    _configure_logging()
    log.info("octantis.starting", version="0.1.0")

    workflow = build_workflow()
    consumer = RedpandaConsumer(settings.redpanda)
    pre_filter, batcher, sampler = _build_pipeline()

    stop_event = asyncio.Event()

    def _handle_signal(*_) -> None:
        log.info("octantis.shutdown_signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    await consumer.start()
    log.info(
        "octantis.ready",
        topic=settings.redpanda.topic,
        batch_window_s=settings.pipeline.batch_window_seconds,
        sampler_cooldown_s=settings.pipeline.sampler_cooldown_seconds,
    )

    # ── Pipeline: Consumer → Pre-filter → Batcher → Sampler → LLM ──────────
    #
    # 1. Pre-filter drops obviously benign events before batching
    #    (avoids polluting batches with health checks / boring metrics)
    # 2. Batcher accumulates events per workload and merges them into
    #    one context-rich event before calling the LLM
    # 3. Sampler suppresses identical fingerprints within the cooldown
    #    window to avoid repeated LLM calls for the same ongoing issue

    async def _filtered_stream():
        async for event in consumer.events():
            if stop_event.is_set():
                return
            if pre_filter.should_analyze(event):
                yield event
            # else: silently dropped — logged inside PreFilter at DEBUG level

    try:
        async for batch in batcher.run(_filtered_stream()):
            if stop_event.is_set():
                break

            if not sampler.should_analyze(batch):
                continue  # suppressed — logged inside Sampler

            log.info(
                "octantis.batch.invoking_llm",
                event_id=batch.event_id,
                source=batch.source,
                metrics_count=len(batch.metrics),
                logs_count=len(batch.logs),
            )

            try:
                result = await workflow.ainvoke({"event": batch})
                analysis = result.get("analysis")
                notifications = result.get("notifications_sent", [])
                log.info(
                    "octantis.batch.processed",
                    event_id=batch.event_id,
                    severity=analysis.severity if analysis else None,
                    notified=notifications,
                    sampler_stats=sampler.stats(),
                )
            except Exception as exc:
                log.error(
                    "octantis.batch.error",
                    event_id=batch.event_id,
                    error=str(exc),
                    exc_info=True,
                )
    finally:
        await consumer.stop()
        log.info("octantis.stopped", sampler_stats=sampler.stats())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
