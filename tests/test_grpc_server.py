"""Unit tests for the gRPC servicer."""

import asyncio

import pytest
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from octantis.receivers.grpc_server import OTLPGrpcServicer
from octantis.receivers.parser import OTLPParser


def _metrics_request() -> ExportMetricsServiceRequest:
    req = ExportMetricsServiceRequest()
    ParseDict(
        {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "cpu",
                                    "gauge": {"dataPoints": [{"asDouble": 50.0}]},
                                }
                            ]
                        }
                    ],
                }
            ]
        },
        req,
    )
    return req


def _logs_request() -> ExportLogsServiceRequest:
    req = ExportLogsServiceRequest()
    ParseDict(
        {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]
                    },
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "body": {"stringValue": "error msg"},
                                    "severityText": "ERROR",
                                }
                            ]
                        }
                    ],
                }
            ]
        },
        req,
    )
    return req


@pytest.fixture
def queue():
    return asyncio.Queue(maxsize=10)


@pytest.fixture
def servicer(queue):
    return OTLPGrpcServicer(queue, OTLPParser())


async def test_metrics_export_enqueues(servicer, queue):
    resp = await servicer._handle_metrics(_metrics_request())
    assert resp is not None
    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.event_type == "metric"
    assert event.source == "svc"


async def test_logs_export_enqueues(servicer, queue):
    resp = await servicer._handle_logs(_logs_request())
    assert resp is not None
    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.event_type == "log"


async def test_trace_export_ignored(servicer, queue):
    req = ExportTraceServiceRequest()
    resp = await servicer._handle_traces(req)
    assert resp is not None
    assert queue.qsize() == 0


async def test_queue_full_drops_event(queue):
    small_queue = asyncio.Queue(maxsize=1)
    servicer = OTLPGrpcServicer(small_queue, OTLPParser())

    # Fill the queue
    await servicer._handle_metrics(_metrics_request())
    assert small_queue.qsize() == 1

    # This should drop, not block
    await servicer._handle_metrics(_metrics_request())
    assert small_queue.qsize() == 1  # still 1, second was dropped


async def test_parse_error_returns_success(servicer, queue):
    # Empty request — parser returns an event (not None), so this tests graceful handling
    req = ExportMetricsServiceRequest()
    resp = await servicer._handle_metrics(req)
    assert resp is not None  # always returns response
