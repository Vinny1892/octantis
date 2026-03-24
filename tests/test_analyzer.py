"""Unit tests for the analyzer node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.analyzer import analyzer_node
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import EnrichedEvent, InfraEvent, OTelResource


def _make_enriched_event(event_type: str = "metric") -> EnrichedEvent:
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
    return EnrichedEvent(original=event)


@pytest.mark.asyncio
async def test_analyzer_critical_response():
    """Analyzer correctly parses CRITICAL severity from LLM."""
    enriched = _make_enriched_event()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(
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
        new=AsyncMock(return_value=mock_response),
    ):
        result = await analyzer_node({"enriched_event": enriched})

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.CRITICAL
    assert analysis.confidence == 0.95
    assert not analysis.is_transient
    assert "api-server" in analysis.affected_components


@pytest.mark.asyncio
async def test_analyzer_not_a_problem():
    """Analyzer correctly parses NOT_A_PROBLEM."""
    enriched = _make_enriched_event()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(
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
        new=AsyncMock(return_value=mock_response),
    ):
        result = await analyzer_node({"enriched_event": enriched})

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.NOT_A_PROBLEM
    assert analysis.is_transient
    assert not analysis.severity.should_notify


@pytest.mark.asyncio
async def test_analyzer_parse_error_fallback():
    """Analyzer falls back to MODERATE on LLM parse error."""
    enriched = _make_enriched_event()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "this is not valid json"

    with patch(
        "octantis.graph.nodes.analyzer.acompletion",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await analyzer_node({"enriched_event": enriched})

    analysis: SeverityAnalysis = result["analysis"]
    assert analysis.severity == Severity.MODERATE
    assert analysis.confidence == 0.5


@pytest.mark.asyncio
async def test_analyzer_preserves_state():
    """Analyzer node preserves existing state fields."""
    enriched = _make_enriched_event()
    initial_state = {"enriched_event": enriched, "notifications_sent": []}

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(
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
        new=AsyncMock(return_value=mock_response),
    ):
        result = await analyzer_node(initial_state)

    assert result["notifications_sent"] == []
    assert result["analysis"].severity == Severity.LOW
