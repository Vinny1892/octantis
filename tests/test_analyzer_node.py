"""Unit tests for analyzer node — _build_user_message branches and analyzer_node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.analyzer import _build_user_message, analyzer_node
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import (
    InfraEvent,
    InvestigationResult,
    K8sResource,
    LogRecord,
    MCPQueryRecord,
    MetricDataPoint,
)


def _make_event(**kwargs) -> InfraEvent:
    defaults = {
        "event_id": "ana-001",
        "event_type": "metric",
        "source": "api-server",
        "resource": K8sResource(
            service_name="api-server",
            k8s_namespace="production",
            k8s_pod_name="api-abc",
        ),
        "metrics": [MetricDataPoint(name="cpu_usage", value=95.0)],
    }
    defaults.update(kwargs)
    return InfraEvent(**defaults)


def _make_investigation(**kwargs) -> InvestigationResult:
    defaults = {
        "original_event": _make_event(),
        "evidence_summary": "CPU spike detected, 15 error logs found",
    }
    defaults.update(kwargs)
    return InvestigationResult(**defaults)


# ─── _build_user_message branches ─────────────────────────────────────────


def test_build_user_message_basic():
    state = {"investigation": _make_investigation()}
    msg = _build_user_message(state)
    assert "Analyze this infrastructure event" in msg
    assert "api-server" in msg


def test_build_user_message_with_queries():
    inv = _make_investigation(
        queries_executed=[
            MCPQueryRecord(
                tool_name="query_prometheus",
                query='rate(http_requests_total{status="500"}[5m])',
                result_summary="0.05 req/s",
                duration_ms=120.0,
                datasource="promql",
            ),
        ]
    )
    state = {"investigation": inv}
    msg = _build_user_message(state)
    assert "## MCP Query Results" in msg
    assert "query_prometheus" in msg
    assert "promql" in msg


def test_build_user_message_with_query_error():
    inv = _make_investigation(
        queries_executed=[
            MCPQueryRecord(
                tool_name="query_loki",
                query='{namespace="prod"}',
                result_summary="timeout",
                duration_ms=5000.0,
                datasource="logql",
                error="timeout",
            ),
        ]
    )
    state = {"investigation": inv}
    msg = _build_user_message(state)
    assert "[ERROR: timeout]" in msg


def test_build_user_message_with_evidence():
    inv = _make_investigation(evidence_summary="High memory usage detected")
    state = {"investigation": inv}
    msg = _build_user_message(state)
    assert "## Investigation Summary" in msg
    assert "High memory usage detected" in msg


def test_build_user_message_with_metrics():
    event = _make_event(metrics=[MetricDataPoint(name="cpu_usage", value=95.0)])
    inv = _make_investigation(original_event=event)
    state = {"investigation": inv}
    msg = _build_user_message(state)
    assert "## Raw Trigger Metrics" in msg
    assert "cpu_usage" in msg


def test_build_user_message_with_logs():
    event = _make_event(
        logs=[
            LogRecord(body="ERROR: OOM killed", severity_text="ERROR"),
        ]
    )
    inv = _make_investigation(original_event=event)
    state = {"investigation": inv}
    msg = _build_user_message(state)
    assert "## Recent Trigger Logs" in msg


def test_build_user_message_mcp_degraded():
    inv = _make_investigation(mcp_degraded=True)
    state = {"investigation": inv}
    msg = _build_user_message(state)
    assert "MCP servers were unavailable" in msg


# ─── analyzer_node ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyzer_node_valid_response():
    state = {"investigation": _make_investigation()}

    analysis_json = json.dumps(
        {
            "severity": "CRITICAL",
            "confidence": 0.95,
            "reasoning": "Service is experiencing OOM kills",
            "affected_components": ["api-server"],
            "is_transient": False,
        }
    )

    mock_response = MagicMock()
    mock_response.choices[0].message.content = analysis_json
    mock_response.get.return_value = MagicMock(prompt_tokens=400, completion_tokens=100)

    with patch(
        "octantis.graph.nodes.analyzer.acompletion", new=AsyncMock(return_value=mock_response)
    ):
        result = await analyzer_node(state)

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.CRITICAL
    assert analysis.confidence == 0.95
    assert "OOM" in analysis.reasoning


@pytest.mark.asyncio
async def test_analyzer_node_invalid_json_fallback():
    state = {"investigation": _make_investigation()}

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "This is not valid JSON"
    mock_response.get.return_value = MagicMock(prompt_tokens=400, completion_tokens=50)

    with patch(
        "octantis.graph.nodes.analyzer.acompletion", new=AsyncMock(return_value=mock_response)
    ):
        result = await analyzer_node(state)

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.MODERATE
    assert analysis.confidence == 0.5
    assert "Parse error" in analysis.reasoning
