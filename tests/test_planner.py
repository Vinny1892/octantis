"""Unit tests for the planner node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.planner import _build_user_message, planner_node
from octantis.models.action_plan import ActionPlan, StepType
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import (
    AWSResource,
    DockerResource,
    InfraEvent,
    InvestigationResult,
    K8sResource,
    MetricDataPoint,
)


def _make_state(resource=None, severity=Severity.CRITICAL):
    if resource is None:
        resource = K8sResource(
            service_name="api-server",
            k8s_namespace="production",
            k8s_pod_name="api-server-abc",
            k8s_node_name="node-1",
            k8s_deployment_name="api-server",
        )
    event = InfraEvent(
        event_id="plan-001",
        event_type="metric",
        source="api-server",
        resource=resource,
        metrics=[MetricDataPoint(name="cpu_usage", value=95.0)],
    )
    investigation = InvestigationResult(
        original_event=event,
        evidence_summary="CPU at 95%, pod restarting, 23 error logs",
    )
    analysis = SeverityAnalysis(
        severity=severity,
        confidence=0.92,
        reasoning="Service is down due to OOM",
        affected_components=["api-server", "database"],
        is_transient=False,
    )
    return {"investigation": investigation, "analysis": analysis}


# ─── _build_user_message ───────────────────────────────────────────────────


def test_build_user_message_k8s():
    state = _make_state()
    msg = _build_user_message(state)
    assert "Kubernetes namespace: production" in msg
    assert "Pod: api-server-abc" in msg
    assert "CRITICAL" in msg
    assert "Service is down due to OOM" in msg


def test_build_user_message_docker():
    resource = DockerResource(
        service_name="nginx",
        container_name="nginx-1",
        image_name="nginx:1.25",
    )
    state = _make_state(resource=resource)
    msg = _build_user_message(state)
    assert "Container: nginx-1" in msg
    assert "Image: nginx:1.25" in msg


def test_build_user_message_aws():
    resource = AWSResource(
        service_name="api",
        instance_id="i-abc123",
        cloud_region="us-east-1",
    )
    state = _make_state(resource=resource)
    msg = _build_user_message(state)
    assert "Instance: i-abc123" in msg
    assert "Region: us-east-1" in msg


# ─── planner_node ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_planner_valid_response():
    state = _make_state()

    plan_json = json.dumps(
        {
            "title": "Fix OOM crash",
            "summary": "Increase memory limits and restart",
            "steps": [
                {
                    "order": 1,
                    "type": "investigate",
                    "title": "Check memory usage",
                    "description": "Review container memory metrics",
                },
                {
                    "order": 2,
                    "type": "execute",
                    "title": "Increase limits",
                    "description": "Patch deployment with higher memory limits",
                    "command": "kubectl set resources deployment/api-server -n production --limits=memory=1Gi",
                },
            ],
            "escalate_to": ["team-sre"],
            "estimated_resolution_minutes": 20,
        }
    )

    mock_response = MagicMock()
    mock_response.choices[0].message.content = plan_json
    mock_response.get.return_value = MagicMock(prompt_tokens=300, completion_tokens=200)

    with patch(
        "octantis.graph.nodes.planner.acompletion", new=AsyncMock(return_value=mock_response)
    ):
        result = await planner_node(state)

    plan: ActionPlan = result["action_plan"]
    assert plan.title == "Fix OOM crash"
    assert len(plan.steps) == 2
    assert plan.steps[0].type == StepType.INVESTIGATE
    assert plan.steps[1].type == StepType.EXECUTE
    assert plan.escalate_to == ["team-sre"]


@pytest.mark.asyncio
async def test_planner_unknown_step_type_coerced():
    """Unknown step types are coerced to INVESTIGATE."""
    state = _make_state()

    plan_json = json.dumps(
        {
            "title": "Fix issue",
            "summary": "Unknown step type",
            "steps": [
                {
                    "order": 1,
                    "type": "custom_unknown_type",
                    "title": "Do something",
                    "description": "desc",
                }
            ],
        }
    )

    mock_response = MagicMock()
    mock_response.choices[0].message.content = plan_json
    mock_response.get.return_value = MagicMock(prompt_tokens=100, completion_tokens=100)

    with patch(
        "octantis.graph.nodes.planner.acompletion", new=AsyncMock(return_value=mock_response)
    ):
        result = await planner_node(state)

    plan: ActionPlan = result["action_plan"]
    assert plan.steps[0].type == StepType.INVESTIGATE


@pytest.mark.asyncio
async def test_planner_invalid_json_fallback():
    """Invalid JSON falls back to manual investigation plan."""
    state = _make_state()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "This is not JSON at all"
    mock_response.get.return_value = MagicMock(prompt_tokens=100, completion_tokens=50)

    with patch(
        "octantis.graph.nodes.planner.acompletion", new=AsyncMock(return_value=mock_response)
    ):
        result = await planner_node(state)

    plan: ActionPlan = result["action_plan"]
    assert "parse error" in plan.title.lower()
    assert len(plan.steps) == 1
    assert plan.steps[0].type == StepType.INVESTIGATE
    assert "Manual investigation required" in plan.steps[0].title
