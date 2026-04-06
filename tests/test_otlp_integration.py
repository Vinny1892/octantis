"""Integration tests for the full OTLP receiver stack."""

import asyncio
import json

import grpc
import pytest
from aiohttp import ClientSession
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2_grpc import (
    MetricsServiceStub,
)

from octantis.config import OTLPSettings
from octantis.receivers.receiver import OTLPReceiver
from tests.fixtures.otlp_payloads import METRICS_JSON, metrics_proto


@pytest.fixture
def free_ports():
    """Return two free ports for gRPC and HTTP."""
    import socket

    socks = []
    ports = []
    for _ in range(2):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        ports.append(s.getsockname()[1])
        socks.append(s)
    for s in socks:
        s.close()
    return ports[0], ports[1]


@pytest.fixture
async def receiver(free_ports):
    grpc_port, http_port = free_ports
    config = OTLPSettings(
        grpc_port=grpc_port,
        http_port=http_port,
        grpc_enabled=True,
        http_enabled=True,
        queue_max_size=100,
    )
    recv = OTLPReceiver(config)
    await recv.start()
    yield recv, grpc_port, http_port
    await recv.stop()


async def test_grpc_round_trip(receiver):
    recv, grpc_port, _ = receiver
    channel = grpc.aio.insecure_channel(f"localhost:{grpc_port}")
    stub = MetricsServiceStub(channel)

    request = metrics_proto()
    response = await stub.Export(request)
    assert isinstance(response, ExportMetricsServiceResponse)

    # Verify event reached queue
    event = await asyncio.wait_for(recv._queue.get(), timeout=2.0)
    assert event.event_type == "metric"
    assert event.resource.service_name == "k8s-app"
    assert len(event.metrics) == 3

    await channel.close()


async def test_http_round_trip(receiver):
    recv, _, http_port = receiver
    async with ClientSession() as session:
        resp = await session.post(
            f"http://localhost:{http_port}/v1/metrics",
            data=json.dumps(METRICS_JSON),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200

    event = await asyncio.wait_for(recv._queue.get(), timeout=2.0)
    assert event.event_type == "metric"
    assert event.resource.service_name == "k8s-app"


async def test_http_404_unknown_path(receiver):
    _, _, http_port = receiver
    async with ClientSession() as session:
        resp = await session.post(f"http://localhost:{http_port}/v1/unknown")
        assert resp.status == 404


async def test_http_415_bad_content_type(receiver):
    _, _, http_port = receiver
    async with ClientSession() as session:
        resp = await session.post(
            f"http://localhost:{http_port}/v1/metrics",
            data=b"text",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status == 415


async def test_concurrent_grpc_and_http(receiver):
    recv, grpc_port, http_port = receiver

    # Send via gRPC
    channel = grpc.aio.insecure_channel(f"localhost:{grpc_port}")
    stub = MetricsServiceStub(channel)

    async def send_grpc():
        await stub.Export(metrics_proto())

    async def send_http():
        async with ClientSession() as session:
            await session.post(
                f"http://localhost:{http_port}/v1/metrics",
                data=json.dumps(METRICS_JSON),
                headers={"Content-Type": "application/json"},
            )

    await asyncio.gather(send_grpc(), send_http())

    # Both events should be in queue
    events = []
    for _ in range(2):
        event = await asyncio.wait_for(recv._queue.get(), timeout=2.0)
        events.append(event)

    assert len(events) == 2
    assert all(e.event_type == "metric" for e in events)

    await channel.close()


async def test_transport_disabled(free_ports):
    grpc_port, http_port = free_ports
    config = OTLPSettings(
        grpc_port=grpc_port,
        http_port=http_port,
        grpc_enabled=False,
        http_enabled=True,
        queue_max_size=100,
    )
    recv = OTLPReceiver(config)
    await recv.start()

    # gRPC should be refused
    channel = grpc.aio.insecure_channel(f"localhost:{grpc_port}")
    stub = MetricsServiceStub(channel)
    with pytest.raises(grpc.aio.AioRpcError):
        await stub.Export(metrics_proto())

    # HTTP should work
    async with ClientSession() as session:
        resp = await session.post(
            f"http://localhost:{http_port}/v1/metrics",
            data=json.dumps(METRICS_JSON),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200

    await channel.close()
    await recv.stop()
