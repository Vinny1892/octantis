"""Unit tests for model properties and edge cases."""

from octantis.models.analysis import Severity
from octantis.models.event import (
    AWSResource,
    DockerResource,
    InfraEvent,
    InvestigationResult,
    K8sResource,
    LogRecord,
    MCPQueryRecord,
    MetricDataPoint,
    OTelResource,
)

# ─── OTelResource.context_summary ─────────────────────────────────────────


def test_otel_resource_context_summary():
    r = OTelResource(service_name="my-svc", host_name="node-1")
    s = r.context_summary()
    assert "Service: my-svc" in s
    assert "Host: node-1" in s


def test_otel_resource_context_summary_no_host():
    r = OTelResource(service_name="my-svc")
    s = r.context_summary()
    assert "Service: my-svc" in s
    assert "Host" not in s


def test_otel_resource_context_summary_no_service():
    r = OTelResource()
    s = r.context_summary()
    assert "unknown" in s


# ─── K8sResource.context_summary ──────────────────────────────────────────


def test_k8s_resource_full():
    r = K8sResource(
        service_name="api",
        k8s_namespace="prod",
        k8s_pod_name="api-abc",
        k8s_deployment_name="api",
        k8s_node_name="node-1",
    )
    s = r.context_summary()
    assert "Namespace: prod" in s
    assert "Pod: api-abc" in s
    assert "Deployment: api" in s
    assert "Node: node-1" in s


def test_k8s_resource_minimal():
    r = K8sResource(service_name="api")
    s = r.context_summary()
    assert "Service: api" in s
    assert "Namespace: unknown" in s


# ─── DockerResource.context_summary ───────────────────────────────────────


def test_docker_resource_full():
    r = DockerResource(
        service_name="nginx",
        container_name="nginx-1",
        image_name="nginx:1.25",
        container_id="abc123def456789",
        host_name="docker-host",
    )
    s = r.context_summary()
    assert "Container: nginx-1" in s
    assert "Image: nginx:1.25" in s
    assert "Container ID: abc123def456" in s
    assert "Host: docker-host" in s


def test_docker_resource_minimal():
    r = DockerResource(service_name="nginx")
    s = r.context_summary()
    assert "Service: nginx" in s


# ─── AWSResource.context_summary ──────────────────────────────────────────


def test_aws_resource_full():
    r = AWSResource(
        service_name="api",
        instance_id="i-abc123",
        cloud_region="us-east-1",
        aws_service="ec2",
        account_id="123456789012",
    )
    s = r.context_summary()
    assert "Instance: i-abc123" in s
    assert "Region: us-east-1" in s
    assert "AWS Service: ec2" in s
    assert "Account: 123456789012" in s


def test_aws_resource_minimal():
    r = AWSResource(service_name="api")
    s = r.context_summary()
    assert "Service: api" in s


# ─── InvestigationResult.summary ──────────────────────────────────────────


def _make_event(**kwargs) -> InfraEvent:
    defaults = {
        "event_id": "test-001",
        "event_type": "metric",
        "source": "api-server",
        "resource": K8sResource(service_name="api-server", k8s_namespace="prod"),
    }
    defaults.update(kwargs)
    return InfraEvent(**defaults)


def test_investigation_summary_basic():
    inv = InvestigationResult(original_event=_make_event())
    s = inv.summary
    assert "api-server" in s
    assert "metric" in s


def test_investigation_summary_with_metrics():
    event = _make_event(metrics=[MetricDataPoint(name="cpu", value=95.0, unit="%")])
    inv = InvestigationResult(original_event=event)
    s = inv.summary
    assert "cpu=95.0%" in s


def test_investigation_summary_with_logs():
    event = _make_event(logs=[LogRecord(body="ERROR: OOM killed")])
    inv = InvestigationResult(original_event=event)
    s = inv.summary
    assert "OOM killed" in s


def test_investigation_summary_with_evidence():
    inv = InvestigationResult(
        original_event=_make_event(),
        evidence_summary="CPU spike detected",
    )
    s = inv.summary
    assert "CPU spike detected" in s


def test_investigation_summary_with_queries():
    inv = InvestigationResult(
        original_event=_make_event(),
        queries_executed=[
            MCPQueryRecord(
                tool_name="q",
                query="q",
                result_summary="r",
                duration_ms=100,
                datasource="promql",
            )
        ],
    )
    s = inv.summary
    assert "1 MCP queries" in s


def test_investigation_summary_mcp_degraded():
    inv = InvestigationResult(original_event=_make_event(), mcp_degraded=True)
    s = inv.summary
    assert "MCP servers were unavailable" in s


def test_investigation_summary_budget_exhausted():
    inv = InvestigationResult(original_event=_make_event(), budget_exhausted=True)
    s = inv.summary
    assert "budget exhausted" in s.lower()


# ─── Severity properties ──────────────────────────────────────────────────


def test_severity_should_notify():
    assert Severity.CRITICAL.should_notify is True
    assert Severity.MODERATE.should_notify is True
    assert Severity.LOW.should_notify is False
    assert Severity.NOT_A_PROBLEM.should_notify is False


def test_severity_color_hex():
    assert Severity.CRITICAL.color_hex == "#FF0000"
    assert Severity.NOT_A_PROBLEM.color_hex == "#00FF00"


def test_severity_discord_color():
    assert Severity.CRITICAL.discord_color == 0xFF0000
    assert isinstance(Severity.LOW.discord_color, int)


def test_severity_emoji():
    assert ":red_circle:" in Severity.CRITICAL.emoji
    assert ":white_check_mark:" in Severity.NOT_A_PROBLEM.emoji
