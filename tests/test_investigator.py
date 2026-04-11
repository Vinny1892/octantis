"""Unit tests for the investigator node."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.investigator import investigate_node
from octantis.models.event import (
    AWSResource,
    DockerResource,
    InfraEvent,
    InvestigationResult,
    K8sResource,
    MetricDataPoint,
)


def _make_event(
    source="api-server",
    ns="production",
    pod="api-abc",
) -> InfraEvent:
    return InfraEvent(
        event_id="inv-001",
        event_type="metric",
        source=source,
        resource=K8sResource(
            service_name=source,
            k8s_namespace=ns,
            k8s_pod_name=pod,
        ),
        metrics=[MetricDataPoint(name="cpu_usage", value=95.0)],
    )


def _make_mcp_manager(tools=None, degraded=False, degraded_servers=None):
    manager = MagicMock()
    manager.get_tools.return_value = tools or []
    manager.is_degraded = degraded
    manager.get_degraded_servers.return_value = degraded_servers or []
    return manager


@pytest.mark.asyncio
async def test_investigate_degraded_mode_no_tools():
    """When no MCP tools are available, investigation returns degraded result."""
    event = _make_event()
    manager = _make_mcp_manager(tools=[], degraded=True, degraded_servers=["grafana"])
    state = {"event": event}

    result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert investigation.mcp_degraded is True
    assert investigation.original_event.event_id == "inv-001"
    assert len(investigation.queries_executed) == 0
    assert "MCP servers unavailable" in investigation.evidence_summary


@pytest.mark.asyncio
async def test_investigate_with_tools_llm_no_tool_calls():
    """When LLM decides not to use tools, investigation returns with zero queries."""
    event = _make_event()

    mock_tool = MagicMock()
    mock_tool.name = "query_prometheus"
    mock_tool.description = "Query Prometheus"
    mock_tool.args_schema = None

    manager = _make_mcp_manager(tools=[mock_tool])

    # Mock LLM response with no tool calls
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Event appears benign based on trigger data."
    mock_response.choices[0].message.tool_calls = None
    mock_response.get.return_value = MagicMock(prompt_tokens=200, completion_tokens=100)

    state = {"event": event}

    with patch(
        "litellm.acompletion",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert investigation.mcp_degraded is False
    assert len(investigation.queries_executed) == 0
    assert "benign" in investigation.evidence_summary.lower()


@pytest.mark.asyncio
async def test_investigate_preserves_event_in_result():
    """Investigation result contains the original trigger event."""
    event = _make_event(source="worker", ns="staging", pod="worker-xyz")
    manager = _make_mcp_manager(tools=[], degraded=True, degraded_servers=["grafana"])
    state = {"event": event}

    result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert investigation.original_event.source == "worker"
    assert investigation.original_event.resource.k8s_namespace == "staging"
    assert isinstance(investigation.original_event.resource, K8sResource)


# ─── Docker & AWS Trigger Context Tests ─────────────────────────────────────


def _make_docker_event() -> InfraEvent:
    return InfraEvent(
        event_id="inv-docker-001",
        event_type="metric",
        source="nginx-proxy",
        resource=DockerResource(
            service_name="nginx-proxy",
            container_name="nginx-proxy-1",
            container_id="abc123def456",
            image_name="nginx:1.25",
            host_name="docker-host-01",
        ),
        metrics=[MetricDataPoint(name="node_cpu_seconds_total", value=92.5)],
    )


def _make_aws_event() -> InfraEvent:
    return InfraEvent(
        event_id="inv-aws-001",
        event_type="metric",
        source="api-service",
        resource=AWSResource(
            service_name="api-service",
            instance_id="i-0abc123def456",
            cloud_region="us-east-1",
            aws_service="ec2",
            account_id="123456789012",
        ),
        metrics=[MetricDataPoint(name="node_cpu_seconds_total", value=88.0)],
    )


@pytest.mark.asyncio
async def test_investigate_docker_trigger_context():
    """Investigation with Docker resource includes container context."""
    event = _make_docker_event()
    manager = _make_mcp_manager(tools=[], degraded=True, degraded_servers=["grafana"])
    state = {"event": event}

    result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert isinstance(investigation.original_event.resource, DockerResource)
    assert investigation.original_event.resource.container_name == "nginx-proxy-1"
    summary = investigation.summary
    assert "Container: nginx-proxy-1" in summary
    assert "Image: nginx:1.25" in summary


@pytest.mark.asyncio
async def test_investigate_aws_trigger_context():
    """Investigation with AWS resource includes cloud context."""
    event = _make_aws_event()
    manager = _make_mcp_manager(tools=[], degraded=True, degraded_servers=["grafana"])
    state = {"event": event}

    result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert isinstance(investigation.original_event.resource, AWSResource)
    assert investigation.original_event.resource.instance_id == "i-0abc123def456"
    summary = investigation.summary
    assert "Instance: i-0abc123def456" in summary
    assert "Region: us-east-1" in summary


@pytest.mark.asyncio
async def test_investigate_docker_with_tools_llm_no_calls():
    """Docker event with tools but LLM decides no queries needed."""
    event = _make_docker_event()

    mock_tool = MagicMock()
    mock_tool.name = "docker_inspect"
    mock_tool.description = "Inspect Docker container"
    mock_tool.args_schema = None

    manager = _make_mcp_manager(tools=[mock_tool])

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Docker container nginx-proxy-1 shows high CPU."
    mock_response.choices[0].message.tool_calls = None
    mock_response.get.return_value = MagicMock(prompt_tokens=200, completion_tokens=100)

    state = {"event": event}

    with patch(
        "litellm.acompletion",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert not investigation.mcp_degraded
    assert (
        "docker" in investigation.evidence_summary.lower()
        or "nginx" in investigation.evidence_summary.lower()
    )
