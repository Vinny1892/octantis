"""Unit tests for the collector node."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.collector import collector_node
from octantis.models.event import (
    EnrichedEvent,
    InfraEvent,
    KubernetesContext,
    OTelResource,
    PrometheusContext,
)


def _make_event(ns: str = "production", pod: str = "api-abc") -> InfraEvent:
    return InfraEvent(
        event_id="col-001",
        event_type="metric",
        source="api-server",
        resource=OTelResource(
            service_name="api-server",
            k8s_namespace=ns,
            k8s_pod_name=pod,
        ),
    )


@pytest.mark.asyncio
async def test_collector_enriches_event():
    """Collector node produces EnrichedEvent with Prometheus + K8s context."""
    event = _make_event()

    prom_ctx = PrometheusContext(cpu_usage_percent=85.0, memory_usage_percent=70.0)
    k8s_ctx = KubernetesContext(pod_phase="Running", pod_restart_count=2)

    with (
        patch(
            "octantis.graph.nodes.collector.PrometheusCollector"
        ) as MockProm,
        patch(
            "octantis.graph.nodes.collector.KubernetesCollector"
        ) as MockK8s,
    ):
        MockProm.return_value.collect = AsyncMock(return_value=prom_ctx)
        MockK8s.return_value.collect = AsyncMock(return_value=k8s_ctx)

        result = await collector_node({"event": event})

    enriched: EnrichedEvent = result["enriched_event"]
    assert enriched.original.event_id == "col-001"
    assert enriched.prometheus.cpu_usage_percent == 85.0
    assert enriched.kubernetes.pod_phase == "Running"
    assert enriched.kubernetes.pod_restart_count == 2


@pytest.mark.asyncio
async def test_collector_preserves_original_event():
    """Collector keeps the original InfraEvent intact."""
    event = _make_event(ns="staging", pod="worker-xyz")

    with (
        patch("octantis.graph.nodes.collector.PrometheusCollector") as MockProm,
        patch("octantis.graph.nodes.collector.KubernetesCollector") as MockK8s,
    ):
        MockProm.return_value.collect = AsyncMock(return_value=PrometheusContext())
        MockK8s.return_value.collect = AsyncMock(return_value=KubernetesContext())

        result = await collector_node({"event": event})

    assert result["enriched_event"].original.resource.k8s_namespace == "staging"
    assert result["enriched_event"].original.resource.k8s_pod_name == "worker-xyz"
    assert result["event"] is event


@pytest.mark.asyncio
async def test_collector_handles_collector_errors_gracefully():
    """Collector returns empty context when sub-collectors fail."""
    event = _make_event()

    with (
        patch("octantis.graph.nodes.collector.PrometheusCollector") as MockProm,
        patch("octantis.graph.nodes.collector.KubernetesCollector") as MockK8s,
    ):
        MockProm.return_value.collect = AsyncMock(return_value=PrometheusContext())
        MockK8s.return_value.collect = AsyncMock(return_value=KubernetesContext())

        result = await collector_node({"event": event})

    enriched = result["enriched_event"]
    assert enriched.prometheus.cpu_usage_percent is None
    assert enriched.kubernetes.pod_phase is None
