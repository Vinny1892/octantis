"""Collector node: enriches InfraEvent with Prometheus + K8s context."""

import structlog

from octantis.collectors.kubernetes import KubernetesCollector
from octantis.collectors.prometheus import PrometheusCollector
from octantis.config import settings
from octantis.graph.state import AgentState
from octantis.models.event import EnrichedEvent

log = structlog.get_logger(__name__)


async def collector_node(state: AgentState) -> AgentState:
    """Enrich the raw InfraEvent with Prometheus metrics and K8s state."""
    event = state["event"]
    log.info("collector.start", event_id=event.event_id, event_type=event.event_type)

    prom_collector = PrometheusCollector(settings.prometheus.url)
    k8s_collector = KubernetesCollector(
        in_cluster=settings.kubernetes.in_cluster,
        kubeconfig=settings.kubernetes.kubeconfig,
    )

    prom_ctx = await prom_collector.collect(event)
    k8s_ctx = await k8s_collector.collect(event)

    enriched = EnrichedEvent(
        original=event,
        prometheus=prom_ctx,
        kubernetes=k8s_ctx,
    )

    log.info(
        "collector.done",
        event_id=event.event_id,
        cpu=prom_ctx.cpu_usage_percent,
        pod_phase=k8s_ctx.pod_phase,
    )

    return {**state, "enriched_event": enriched}
