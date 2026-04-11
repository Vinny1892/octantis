"""Octantis main entrypoint."""

import asyncio
import signal
import sys

import json

import structlog

from octantis.config import settings
from octantis.graph.workflow import build_workflow
from octantis.mcp_client import MCPServerConfig, MCPClientManager
from octantis.pipeline import FingerprintCooldown, TriggerFilter
from octantis.pipeline.environment_detector import EnvironmentDetector
from octantis.receivers import OTLPReceiver

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
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def _build_mcp_configs() -> list[MCPServerConfig]:
    """Build MCP server configs from settings."""
    configs: list[MCPServerConfig] = []

    if settings.grafana_mcp.url:
        headers = {}
        if settings.grafana_mcp.api_key:
            headers["Authorization"] = f"Bearer {settings.grafana_mcp.api_key}"
        configs.append(
            MCPServerConfig(
                name="grafana",
                slot="observability",
                url=settings.grafana_mcp.url,
                headers=headers,
            )
        )

    if settings.k8s_mcp.url:
        configs.append(
            MCPServerConfig(
                name="k8s",
                slot="platform",
                url=settings.k8s_mcp.url,
            )
        )

    if settings.docker_mcp.url:
        headers = {}
        if settings.docker_mcp.headers:
            try:
                headers = json.loads(settings.docker_mcp.headers)
            except json.JSONDecodeError:
                pass
        configs.append(
            MCPServerConfig(
                name="docker",
                slot="platform",
                url=settings.docker_mcp.url,
                headers=headers,
            )
        )

    if settings.aws_mcp.url:
        headers = {}
        if settings.aws_mcp.headers:
            try:
                headers = json.loads(settings.aws_mcp.headers)
            except json.JSONDecodeError:
                pass
        configs.append(
            MCPServerConfig(
                name="aws",
                slot="platform",
                url=settings.aws_mcp.url,
                headers=headers,
            )
        )

    return configs


def _build_pipeline():
    """Instantiate trigger filter and fingerprint cooldown from settings."""
    cfg = settings.pipeline

    trigger_filter = TriggerFilter.default(
        cpu_threshold=cfg.cpu_threshold,
        memory_threshold=cfg.memory_threshold,
        error_rate_threshold=cfg.error_rate_threshold,
        benign_patterns=cfg.benign_patterns_list,
    )
    cooldown = FingerprintCooldown(
        cooldown_seconds=cfg.cooldown_seconds,
        max_entries=cfg.cooldown_max_entries,
    )
    return trigger_filter, cooldown


async def run() -> None:
    """Main async run loop."""
    _configure_logging()
    log.info("octantis.starting", version="0.2.0")

    # Start metrics server
    if settings.metrics.enabled:
        from octantis.metrics import start_metrics_server

        start_metrics_server(settings.metrics.port)
        log.info("octantis.metrics.started", port=settings.metrics.port)

    # Initialize MCP client
    mcp_configs = _build_mcp_configs()
    mcp_manager = MCPClientManager(
        configs=mcp_configs,
        retry_settings=settings.mcp_retry,
        query_timeout=settings.investigation.timeout_seconds,
    )
    await mcp_manager.connect()

    # Environment detector
    detector = EnvironmentDetector(platform_override=settings.platform.platform)

    workflow = build_workflow(mcp_manager)
    consumer = OTLPReceiver(settings.otlp)
    trigger_filter, cooldown = _build_pipeline()

    stop_event = asyncio.Event()

    def _handle_signal(*_) -> None:
        log.info("octantis.shutdown_signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    await consumer.start()
    log.info(
        "octantis.ready",
        grpc_port=settings.otlp.grpc_port if settings.otlp.grpc_enabled else None,
        http_port=settings.otlp.http_port if settings.otlp.http_enabled else None,
        mcp_degraded=mcp_manager.is_degraded,
        cooldown_s=settings.pipeline.cooldown_seconds,
    )

    # ── Pipeline: Consumer → TriggerFilter → Cooldown → Workflow ──────────
    #
    # 1. TriggerFilter drops obviously benign events (health checks, boring metrics)
    # 2. Cooldown suppresses identical fingerprints within the cooldown window
    # 3. Workflow: investigate (MCP tools) → analyze → plan → notify

    from octantis.metrics import TRIGGER_TOTAL

    try:
        async for event in consumer.events():
            if stop_event.is_set():
                break

            # Trigger filter
            if not trigger_filter.should_investigate(event):
                TRIGGER_TOTAL.labels(outcome="dropped").inc()
                continue

            # Fingerprint cooldown
            if not cooldown.should_investigate(event):
                TRIGGER_TOTAL.labels(outcome="cooldown").inc()
                continue

            # Environment detection
            event = detector.detect(event)

            TRIGGER_TOTAL.labels(outcome="passed").inc()

            log.info(
                "octantis.trigger.invoking_investigation",
                event_id=event.event_id,
                source=event.source,
                metrics_count=len(event.metrics),
                logs_count=len(event.logs),
            )

            try:
                result = await workflow.ainvoke({"event": event})
                analysis = result.get("analysis")
                notifications = result.get("notifications_sent", [])
                investigation = result.get("investigation")
                log.info(
                    "octantis.trigger.processed",
                    event_id=event.event_id,
                    severity=analysis.severity if analysis else None,
                    notified=notifications,
                    queries_count=len(investigation.queries_executed) if investigation else 0,
                    mcp_degraded=investigation.mcp_degraded if investigation else False,
                    cooldown_stats=cooldown.stats(),
                )
            except Exception as exc:
                log.error(
                    "octantis.trigger.error",
                    event_id=event.event_id,
                    error=str(exc),
                    exc_info=True,
                )
    finally:
        await consumer.stop()
        await mcp_manager.close()
        log.info("octantis.stopped", cooldown_stats=cooldown.stats())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
