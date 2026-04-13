"""Async HTTP server implementing OTLP/HTTP endpoints."""

import asyncio
import json
from typing import Any

import structlog
from aiohttp import web
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)

from octantis_plugin_sdk import Event as SDKEvent

from octantis.receivers.parser import OTLPParser

log = structlog.get_logger(__name__)

_ALLOWED_CONTENT_TYPES = {"application/json", "application/x-protobuf"}


def _create_routes(queue: asyncio.Queue[SDKEvent], parser: OTLPParser) -> web.Application:
    """Build the aiohttp application with OTLP routes."""

    async def handle_metrics(request: web.Request) -> web.Response:
        content_type = request.content_type
        if content_type not in _ALLOWED_CONTENT_TYPES:
            return web.Response(status=415)

        body = await request.read()
        try:
            event = _parse_signal(body, content_type, "metrics", parser)
            if event:
                _enqueue(queue, event)
                log.debug(
                    "otlp.http.received",
                    path="/v1/metrics",
                    content_type=content_type,
                    event_type=event.event_type,
                    service_name=event.resource.get("service.name"),
                )
        except Exception as exc:
            log.error(
                "otlp.parse.error", transport="http", error=str(exc), raw_payload=str(body)[:200]
            )
        return web.Response(status=200)

    async def handle_logs(request: web.Request) -> web.Response:
        content_type = request.content_type
        if content_type not in _ALLOWED_CONTENT_TYPES:
            return web.Response(status=415)

        body = await request.read()
        try:
            event = _parse_signal(body, content_type, "logs", parser)
            if event:
                _enqueue(queue, event)
                log.debug(
                    "otlp.http.received",
                    path="/v1/logs",
                    content_type=content_type,
                    event_type=event.event_type,
                    service_name=event.resource.get("service.name"),
                )
        except Exception as exc:
            log.error(
                "otlp.parse.error", transport="http", error=str(exc), raw_payload=str(body)[:200]
            )
        return web.Response(status=200)

    async def handle_traces(request: web.Request) -> web.Response:
        content_type = request.content_type
        if content_type not in _ALLOWED_CONTENT_TYPES:
            return web.Response(status=415)
        log.debug("otlp.trace.ignored", transport="http")
        return web.Response(status=200)

    app = web.Application()
    app.router.add_post("/v1/metrics", handle_metrics)
    app.router.add_post("/v1/logs", handle_logs)
    app.router.add_post("/v1/traces", handle_traces)
    return app


def _parse_signal(
    body: bytes,
    content_type: str,
    signal: str,
    parser: OTLPParser,
) -> SDKEvent | None:
    """Parse an OTLP payload based on signal type and content type."""
    if signal == "metrics":
        if content_type == "application/x-protobuf":
            req = ExportMetricsServiceRequest()
            req.ParseFromString(body)
            return parser.parse_metrics_proto(req)
        data: dict[str, Any] = json.loads(body)
        return parser.parse_metrics_json(data)

    if signal == "logs":
        if content_type == "application/x-protobuf":
            req = ExportLogsServiceRequest()
            req.ParseFromString(body)
            return parser.parse_logs_proto(req)
        data = json.loads(body)
        return parser.parse_logs_json(data)

    return None


def _enqueue(queue: asyncio.Queue[SDKEvent], event: SDKEvent) -> None:
    """Put event on queue, drop if full."""
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        log.warning("otlp.queue.dropped", reason="queue_full", queue_size=queue.qsize())
