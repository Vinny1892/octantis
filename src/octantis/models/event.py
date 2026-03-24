"""Event models for raw and enriched infrastructure events."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OTelResource(BaseModel):
    """OpenTelemetry resource attributes."""

    service_name: str | None = None
    service_namespace: str | None = None
    k8s_namespace: str | None = None
    k8s_pod_name: str | None = None
    k8s_node_name: str | None = None
    k8s_deployment_name: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class MetricDataPoint(BaseModel):
    """A single OTel metric data point."""

    name: str
    value: float
    unit: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LogRecord(BaseModel):
    """An OTel log record."""

    body: str
    severity_text: str | None = None
    severity_number: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InfraEvent(BaseModel):
    """Raw infrastructure event consumed from Redpanda/OTel."""

    event_id: str
    event_type: str  # "metric", "log", "alert", "trace_span"
    source: str  # originating service / exporter
    resource: OTelResource = Field(default_factory=OTelResource)
    metrics: list[MetricDataPoint] = Field(default_factory=list)
    logs: list[LogRecord] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=datetime.utcnow)


class PrometheusContext(BaseModel):
    """Additional Prometheus metrics fetched for context."""

    cpu_usage_percent: float | None = None
    memory_usage_percent: float | None = None
    error_rate_5m: float | None = None
    request_latency_p99_ms: float | None = None
    pod_restart_count: int | None = None
    custom_metrics: dict[str, float] = Field(default_factory=dict)
    queries_run: list[str] = Field(default_factory=list)


class KubernetesContext(BaseModel):
    """Additional K8s state fetched for context."""

    pod_phase: str | None = None
    pod_conditions: list[dict[str, Any]] = Field(default_factory=list)
    pod_restart_count: int | None = None
    node_conditions: list[dict[str, Any]] = Field(default_factory=list)
    deployment_available_replicas: int | None = None
    deployment_desired_replicas: int | None = None
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    node_pressure: dict[str, bool] = Field(default_factory=dict)


class EnrichedEvent(BaseModel):
    """InfraEvent enriched with Prometheus + K8s context."""

    original: InfraEvent
    prometheus: PrometheusContext = Field(default_factory=PrometheusContext)
    kubernetes: KubernetesContext = Field(default_factory=KubernetesContext)
    enriched_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def summary(self) -> str:
        """Human-readable summary for LLM context."""
        parts = [
            f"Event: {self.original.event_type} from {self.original.source}",
            f"Service: {self.original.resource.service_name or 'unknown'}",
            f"Namespace: {self.original.resource.k8s_namespace or 'unknown'}",
        ]
        if self.original.resource.k8s_pod_name:
            parts.append(f"Pod: {self.original.resource.k8s_pod_name}")
        if self.original.metrics:
            metrics_str = ", ".join(
                f"{m.name}={m.value}{m.unit or ''}"
                for m in self.original.metrics[:5]
            )
            parts.append(f"Metrics: {metrics_str}")
        if self.original.logs:
            parts.append(f"Latest log: {self.original.logs[-1].body[:200]}")
        if self.prometheus.cpu_usage_percent is not None:
            parts.append(f"CPU: {self.prometheus.cpu_usage_percent:.1f}%")
        if self.prometheus.memory_usage_percent is not None:
            parts.append(f"Memory: {self.prometheus.memory_usage_percent:.1f}%")
        if self.prometheus.error_rate_5m is not None:
            parts.append(f"Error rate (5m): {self.prometheus.error_rate_5m:.2f}")
        if self.kubernetes.pod_phase:
            parts.append(f"Pod phase: {self.kubernetes.pod_phase}")
        if self.kubernetes.deployment_available_replicas is not None:
            parts.append(
                f"Replicas: {self.kubernetes.deployment_available_replicas}"
                f"/{self.kubernetes.deployment_desired_replicas}"
            )
        return "\n".join(parts)
