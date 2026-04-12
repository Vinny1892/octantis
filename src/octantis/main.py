"""Octantis main entrypoint."""

import asyncio
import signal
import sys

import structlog
from octantis_plugin_sdk import Event as SDKEvent

from octantis.config import settings
from octantis.graph.workflow import build_workflow
from octantis.mcp_client.aggregator import AggregatedMCPManager
from octantis.pipeline.environment_detector import EnvironmentDetector
from octantis.plugins.registry import PluginRegistry, PluginType

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


def _build_pipeline_config() -> dict[str, dict]:
    cfg = settings.pipeline
    return {
        "trigger-filter": {
            "cpu_threshold": cfg.cpu_threshold,
            "memory_threshold": cfg.memory_threshold,
            "error_rate_threshold": cfg.error_rate_threshold,
            "benign_patterns": cfg.benign_patterns_list or None,
        },
        "fingerprint-cooldown": {
            "cooldown_seconds": cfg.cooldown_seconds,
            "max_entries": cfg.cooldown_max_entries,
        },
    }


def _build_notifier_config() -> dict[str, dict]:
    configs: dict[str, dict] = {}
    if settings.slack.enabled:
        configs["slack"] = {
            "webhook_url": settings.slack.webhook_url,
            "bot_token": settings.slack.bot_token,
            "channel": settings.slack.channel,
        }
    if settings.discord.enabled:
        configs["discord"] = {
            "webhook_url": settings.discord.webhook_url,
        }
    return configs


async def run() -> None:
    """Main async run loop."""
    _configure_logging()
    log.info("octantis.starting", version="0.2.0")

    # Start metrics server
    if settings.metrics.enabled:
        from octantis.metrics import start_metrics_server

        start_metrics_server(settings.metrics.port)
        log.info("octantis.metrics.started", port=settings.metrics.port)

    # Plugin registry — discovers all built-in and third-party plugins
    registry = PluginRegistry()
    registry.discover()

    pipeline_config = _build_pipeline_config()
    notifier_config = _build_notifier_config()
    plugin_config: dict[str, dict] = {**pipeline_config, **notifier_config}

    registry.setup_all(plugin_config)

    processors = registry.plugins(PluginType.PROCESSOR)
    log.info(
        "octantis.processors.loaded",
        processors=[p.name for p in processors],
        priorities=[p.priority for p in processors],
    )

    # Receiver — event source via the registry
    receiver_plugins = registry.plugins(PluginType.RECEIVER)
    receiver_plugin = receiver_plugins[0].instance if receiver_plugins else None

    # MCP connectors — per-server plugins (Fork B=1), connected in parallel
    mcp_plugins = registry.plugins(PluginType.MCP)
    active_mcp_instances = [lp.instance for lp in mcp_plugins if lp.instance.manager is not None]
    for mcp_instance in active_mcp_instances:
        await mcp_instance.connect()
    if active_mcp_instances:
        log.info(
            "octantis.mcp.connected",
            servers=[p.name for p in active_mcp_instances],
            connected=[s for p in active_mcp_instances for s in p.get_connected_servers()],
            degraded=[s for p in active_mcp_instances for s in p.get_degraded_servers()],
        )

    # Environment detector
    detector = EnvironmentDetector(platform_override=settings.platform.platform)

    # Aggregator facade for workflow
    mcp_manager = AggregatedMCPManager(active_mcp_instances)

    workflow = build_workflow(mcp_manager)

    stop_event = asyncio.Event()

    def _handle_signal(*_) -> None:
        log.info("octantis.shutdown_signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    # Start the receiver (binds gRPC/HTTP ports)
    if receiver_plugin:
        await receiver_plugin.start()
    log.info(
        "octantis.ready",
        grpc_port=settings.otlp.grpc_port if settings.otlp.grpc_enabled else None,
        http_port=settings.otlp.http_port if settings.otlp.http_enabled else None,
        mcp_degraded=mcp_manager.is_degraded,
        cooldown_s=settings.pipeline.cooldown_seconds,
        processors=[p.name for p in processors],
        receiver=receiver_plugins[0].name if receiver_plugins else None,
    )

    from octantis.metrics import TRIGGER_TOTAL

    try:
        # Consume events from the receiver plugin
        event_source = receiver_plugin if receiver_plugin else None
        if event_source is None:
            log.error("octantis.no_receiver")
            return

        async for event in event_source.events():
            if stop_event.is_set():
                break

            # Run processors in priority order
            dropped = False
            for proc_plugin in processors:
                sdk_event = SDKEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    source=event.source,
                    resource=event.resource.extra if hasattr(event.resource, "extra") else {},
                    metrics=[{"name": m.name, "value": m.value} for m in event.metrics],
                    logs=[{"body": l.body} for l in event.logs],
                )
                result = await proc_plugin.instance.process(sdk_event)
                if result is None:
                    dropped = True
                    outcome = "dropped" if proc_plugin.name == "trigger-filter" else "cooldown"
                    TRIGGER_TOTAL.labels(outcome=outcome).inc()
                    break

            if dropped:
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
                )
            except Exception as exc:
                log.error(
                    "octantis.trigger.error",
                    event_id=event.event_id,
                    error=str(exc),
                    exc_info=True,
                )
    finally:
        if receiver_plugin:
            await receiver_plugin.stop()
        for mcp_instance in active_mcp_instances:
            await mcp_instance.close()
        registry.teardown_all()
        log.info("octantis.stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
