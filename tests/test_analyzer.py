"""Unit tests for the analyzer node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.analyzer import analyzer_node
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import InfraEvent, InvestigationResult, OTelResource


def _make_investigation(event_type: str = "metric") -> InvestigationResult:
    event = InfraEvent(
        event_id="test-001",
        event_type=event_type,
        source="test-service",
        resource=OTelResource(
            service_name="api-server",
            k8s_namespace="production",
            k8s_pod_name="api-server-abc123",
        ),
    )
    return InvestigationResult(
        original_event=event,
        evidence_summary="CPU at 95%, memory at 80%, 3 restarts in last 5 min",
    )


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = json.dumps(data)
    resp.get.return_value = MagicMock(prompt_tokens=100, completion_tokens=50)
    return resp


@pytest.mark.asyncio
async def test_analyzer_critical_response():
    """Analyzer correctly parses CRITICAL severity from LLM."""
    investigation = _make_investigation()

    response = _mock_response(
        {
            "severity": "CRITICAL",
            "confidence": 0.95,
            "reasoning": "Pod is crash-looping with OOMKilled errors",
            "affected_components": ["api-server"],
            "is_transient": False,
            "similar_past_issues": [],
        }
    )

    with patch(
        "octantis.graph.nodes.analyzer.acompletion",
        new=AsyncMock(return_value=response),
    ):
        result = await analyzer_node({"investigation": investigation})

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.CRITICAL
    assert analysis.confidence == 0.95
    assert not analysis.is_transient
    assert "api-server" in analysis.affected_components


@pytest.mark.asyncio
async def test_analyzer_not_a_problem():
    """Analyzer correctly parses NOT_A_PROBLEM."""
    investigation = _make_investigation()

    response = _mock_response(
        {
            "severity": "NOT_A_PROBLEM",
            "confidence": 0.9,
            "reasoning": "Metric spike during scheduled job, expected behavior",
            "affected_components": [],
            "is_transient": True,
            "similar_past_issues": ["nightly-batch-job"],
        }
    )

    with patch(
        "octantis.graph.nodes.analyzer.acompletion",
        new=AsyncMock(return_value=response),
    ):
        result = await analyzer_node({"investigation": investigation})

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.NOT_A_PROBLEM
    assert analysis.is_transient
    assert not analysis.severity.should_notify


@pytest.mark.asyncio
async def test_analyzer_parse_error_fallback():
    """Analyzer falls back to MODERATE on LLM parse error."""
    investigation = _make_investigation()

    resp = MagicMock()
    resp.choices[0].message.content = "this is not valid json"
    resp.get.return_value = MagicMock(prompt_tokens=100, completion_tokens=50)

    with patch(
        "octantis.graph.nodes.analyzer.acompletion",
        new=AsyncMock(return_value=resp),
    ):
        result = await analyzer_node({"investigation": investigation})

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.MODERATE
    assert analysis.confidence == 0.5


@pytest.mark.asyncio
async def test_analyzer_preserves_state():
    """Analyzer node preserves existing state fields."""
    investigation = _make_investigation()
    initial_state = {"investigation": investigation, "notifications_sent": []}

    response = _mock_response(
        {
            "severity": "LOW",
            "confidence": 0.7,
            "reasoning": "Minor CPU spike",
            "affected_components": [],
            "is_transient": True,
            "similar_past_issues": [],
        }
    )

    with patch(
        "octantis.graph.nodes.analyzer.acompletion",
        new=AsyncMock(return_value=response),
    ):
        result = await analyzer_node(initial_state)

    assert result["notifications_sent"] == []
    assert result["analysis"].severity == Severity.LOW
