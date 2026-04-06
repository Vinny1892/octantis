"""Event models for raw and enriched infrastructure events."""

from datetime import UTC, datetime
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LogRecord(BaseModel):
    """An OTel log record."""

    body: str
    severity_text: str | None = None
    severity_number: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InfraEvent(BaseModel):
    """Raw infrastructure event consumed from Redpanda/OTel."""

    event_id: str
    event_type: str  # "metric", "log", "alert", "trace_span"
    source: str  # originating service / exporter
    resource: OTelResource = Field(default_factory=OTelResource)
    metrics: list[MetricDataPoint] = Field(default_factory=list)
    logs: list[LogRecord] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MCPQueryRecord(BaseModel):
    """Record of a single MCP query executed during investigation."""

    tool_name: str
    query: str
    result_summary: str
    duration_ms: float
    datasource: str  # "promql", "logql", "k8s"
    error: str | None = None


class InvestigationResult(BaseModel):
    """Output of the investigate node — replaces EnrichedEvent."""

    original_event: InfraEvent
    queries_executed: list[MCPQueryRecord] = Field(default_factory=list)
    evidence_summary: str = ""
    mcp_servers_used: list[str] = Field(default_factory=list)
    mcp_degraded: bool = False
    budget_exhausted: bool = False
    investigation_duration_s: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0

    @property
    def summary(self) -> str:
        """Human-readable summary for LLM context."""
        parts = [
            f"Event: {self.original_event.event_type} from {self.original_event.source}",
            f"Service: {self.original_event.resource.service_name or 'unknown'}",
            f"Namespace: {self.original_event.resource.k8s_namespace or 'unknown'}",
        ]
        if self.original_event.resource.k8s_pod_name:
            parts.append(f"Pod: {self.original_event.resource.k8s_pod_name}")
        if self.original_event.metrics:
            metrics_str = ", ".join(
                f"{m.name}={m.value}{m.unit or ''}" for m in self.original_event.metrics[:5]
            )
            parts.append(f"Trigger metrics: {metrics_str}")
        if self.original_event.logs:
            parts.append(f"Trigger log: {self.original_event.logs[-1].body[:200]}")
        if self.evidence_summary:
            parts.append(f"Investigation: {self.evidence_summary[:500]}")
        if self.queries_executed:
            parts.append(f"Queries: {len(self.queries_executed)} MCP queries executed")
        if self.mcp_degraded:
            parts.append(
                "WARNING: MCP servers were unavailable — analysis based on trigger data only"
            )
        if self.budget_exhausted:
            parts.append("NOTE: Query budget exhausted — analysis based on partial data")
        return "\n".join(parts)
