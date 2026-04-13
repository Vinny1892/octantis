# SPDX-License-Identifier: AGPL-3.0-or-later
"""Async gRPC server implementing OTLP MetricsService, LogsService, TraceService."""

import asyncio

import grpc
import structlog
from octantis_plugin_sdk import Event as SDKEvent
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import (
    LogsServiceServicer,
    add_LogsServiceServicer_to_server,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2_grpc import (
    MetricsServiceServicer,
    add_MetricsServiceServicer_to_server,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import (
    TraceServiceServicer,
    add_TraceServiceServicer_to_server,
)

from octantis.receivers.parser import OTLPParser

log = structlog.get_logger(__name__)


class OTLPGrpcServicer(MetricsServiceServicer, LogsServiceServicer, TraceServiceServicer):
    """Unified gRPC servicer for all OTLP signal types."""

    def __init__(self, queue: asyncio.Queue[SDKEvent], parser: OTLPParser) -> None:
        self._queue = queue
        self._parser = parser

    async def Export(self, request, context):
        """Route based on request type."""
        if isinstance(request, ExportMetricsServiceRequest):
            return await self._handle_metrics(request)
        if isinstance(request, ExportLogsServiceRequest):
            return await self._handle_logs(request)
        # TraceService.Export
        return await self._handle_traces(request)

    async def _handle_metrics(
        self, request: ExportMetricsServiceRequest
    ) -> ExportMetricsServiceResponse:
        try:
            event = self._parser.parse_metrics_proto(request)
            if event:
                self._enqueue(event, "grpc")
                log.debug(
                    "otlp.grpc.received",
                    event_type=event.event_type,
                    service_name=event.resource.get("service.name"),
                    metrics_count=len(event.metrics),
                    logs_count=len(event.logs),
                )
        except Exception as exc:
            log.error(
                "otlp.parse.error", transport="grpc", error=str(exc), raw_payload=str(request)[:200]
            )
        return ExportMetricsServiceResponse()

    async def _handle_logs(self, request: ExportLogsServiceRequest) -> ExportLogsServiceResponse:
        try:
            event = self._parser.parse_logs_proto(request)
            if event:
                self._enqueue(event, "grpc")
                log.debug(
                    "otlp.grpc.received",
                    event_type=event.event_type,
                    service_name=event.resource.get("service.name"),
                    metrics_count=len(event.metrics),
                    logs_count=len(event.logs),
                )
        except Exception as exc:
            log.error(
                "otlp.parse.error", transport="grpc", error=str(exc), raw_payload=str(request)[:200]
            )
        return ExportLogsServiceResponse()

    async def _handle_traces(self, request) -> ExportTraceServiceResponse:
        log.debug("otlp.trace.ignored", transport="grpc")
        return ExportTraceServiceResponse()

    def _enqueue(self, event: SDKEvent, transport: str) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("otlp.queue.dropped", reason="queue_full", queue_size=self._queue.qsize())


async def create_grpc_server(
    queue: asyncio.Queue[SDKEvent],
    parser: OTLPParser,
    port: int,
) -> grpc.aio.Server:
    """Create and configure the gRPC server (does not start it)."""
    server = grpc.aio.server()
    servicer = OTLPGrpcServicer(queue, parser)
    add_MetricsServiceServicer_to_server(servicer, server)
    add_LogsServiceServicer_to_server(servicer, server)
    add_TraceServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server
