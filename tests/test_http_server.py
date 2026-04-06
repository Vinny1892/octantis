"""Unit tests for the HTTP OTLP server."""

import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)

from octantis.receivers.http_server import _create_routes
from octantis.receivers.parser import OTLPParser


@pytest.fixture
def queue():
    return asyncio.Queue(maxsize=10)


@pytest.fixture
def app(queue):
    return _create_routes(queue, OTLPParser())


@pytest.fixture
async def client(app):
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


async def test_json_metrics_returns_200(client, queue):
    payload = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "http-svc"}}]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "req_count",
                                "gauge": {"dataPoints": [{"asDouble": 10.0}]},
                            }
                        ]
                    }
                ],
            }
        ]
    }
    resp = await client.post(
        "/v1/metrics",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.event_type == "metric"


async def test_protobuf_metrics_returns_200(client, queue):
    req = ExportMetricsServiceRequest()
    ParseDict(
        {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "pb-svc"}}]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "cpu",
                                    "gauge": {"dataPoints": [{"asDouble": 42.0}]},
                                }
                            ]
                        }
                    ],
                }
            ]
        },
        req,
    )
    resp = await client.post(
        "/v1/metrics",
        data=req.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf"},
    )
    assert resp.status == 200
    assert queue.qsize() == 1


async def test_json_logs_returns_200(client, queue):
    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "log-svc"}}]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "test log"},
                                "severityText": "INFO",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    resp = await client.post(
        "/v1/logs",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.event_type == "log"


async def test_traces_returns_200_no_enqueue(client, queue):
    resp = await client.post(
        "/v1/traces",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 200
    assert queue.qsize() == 0


async def test_unsupported_content_type_returns_415(client):
    resp = await client.post(
        "/v1/metrics",
        data=b"text",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status == 415


async def test_unknown_path_returns_404(client):
    resp = await client.post("/v1/unknown")
    assert resp.status == 404


async def test_malformed_json_returns_200(client, queue):
    resp = await client.post(
        "/v1/metrics",
        data=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    # Returns 200 to avoid Collector retry storms
    assert resp.status == 200
    assert queue.qsize() == 0
