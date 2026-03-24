"""Prometheus collector: fetches contextual metrics via PromQL."""

import structlog
from prometheus_api_client import PrometheusConnect

from octantis.models.event import InfraEvent, PrometheusContext

log = structlog.get_logger(__name__)


class PrometheusCollector:
    def __init__(self, url: str, timeout: int = 30) -> None:
        self._client = PrometheusConnect(url=url, disable_ssl=True)
        self._timeout = timeout

    async def collect(self, event: InfraEvent) -> PrometheusContext:
        """Fetch relevant Prometheus metrics for the given event."""
        ctx = PrometheusContext()
        ns = event.resource.k8s_namespace
        pod = event.resource.k8s_pod_name
        service = event.resource.service_name

        queries: list[tuple[str, str]] = []

        if pod and ns:
            queries += [
                (
                    "cpu_usage_percent",
                    f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}",pod="{pod}"}}[5m])) * 100',
                ),
                (
                    "memory_usage_percent",
                    f'(container_memory_working_set_bytes{{namespace="{ns}",pod="{pod}"}} / container_spec_memory_limit_bytes{{namespace="{ns}",pod="{pod}"}}) * 100',
                ),
                (
                    "pod_restart_count",
                    f'kube_pod_container_status_restarts_total{{namespace="{ns}",pod="{pod}"}}',
                ),
            ]

        if service and ns:
            queries += [
                (
                    "error_rate_5m",
                    f'sum(rate(http_requests_total{{namespace="{ns}",service="{service}",status=~"5.."}}[5m]))',
                ),
                (
                    "request_latency_p99_ms",
                    f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{namespace="{ns}",service="{service}"}}[5m])) by (le)) * 1000',
                ),
            ]

        for field_name, query in queries:
            try:
                result = self._client.custom_query(query=query)
                if result:
                    value = float(result[0]["value"][1])
                    setattr(ctx, field_name, value)
                    ctx.queries_run.append(query)
            except Exception as exc:
                log.warning(
                    "prometheus.query_failed",
                    query=query[:80],
                    error=str(exc),
                )

        return ctx
