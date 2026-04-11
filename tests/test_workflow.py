"""Unit tests for graph/workflow.py — build_workflow and _should_notify."""

from unittest.mock import MagicMock, patch

from octantis.graph.workflow import _should_notify, build_workflow
from octantis.models.analysis import Severity, SeverityAnalysis


def _make_analysis(severity: Severity) -> SeverityAnalysis:
    return SeverityAnalysis(
        severity=severity,
        confidence=0.9,
        reasoning="test reasoning for routing",
        affected_components=["svc"],
    )


# ─── _should_notify ────────────────────────────────────────────────────────


def test_should_notify_critical_routes_to_plan():
    state = {"analysis": _make_analysis(Severity.CRITICAL)}
    with patch("octantis.graph.workflow.settings") as mock:
        mock.min_severity_to_notify = "MODERATE"
        assert _should_notify(state) == "plan"


def test_should_notify_moderate_routes_to_plan():
    state = {"analysis": _make_analysis(Severity.MODERATE)}
    with patch("octantis.graph.workflow.settings") as mock:
        mock.min_severity_to_notify = "MODERATE"
        assert _should_notify(state) == "plan"


def test_should_notify_low_routes_to_end():
    state = {"analysis": _make_analysis(Severity.LOW)}
    with patch("octantis.graph.workflow.settings") as mock:
        mock.min_severity_to_notify = "MODERATE"
        assert _should_notify(state) == "end"


def test_should_notify_not_a_problem_routes_to_end():
    state = {"analysis": _make_analysis(Severity.NOT_A_PROBLEM)}
    with patch("octantis.graph.workflow.settings") as mock:
        mock.min_severity_to_notify = "MODERATE"
        assert _should_notify(state) == "end"


def test_should_notify_no_analysis_routes_to_end():
    state = {}
    assert _should_notify(state) == "end"


def test_should_notify_threshold_critical_only():
    """When threshold is CRITICAL, only CRITICAL passes."""
    with patch("octantis.graph.workflow.settings") as mock:
        mock.min_severity_to_notify = "CRITICAL"
        assert _should_notify({"analysis": _make_analysis(Severity.CRITICAL)}) == "plan"
        assert _should_notify({"analysis": _make_analysis(Severity.MODERATE)}) == "end"


def test_should_notify_threshold_low():
    """When threshold is LOW, LOW, MODERATE, and CRITICAL all pass."""
    with patch("octantis.graph.workflow.settings") as mock:
        mock.min_severity_to_notify = "LOW"
        assert _should_notify({"analysis": _make_analysis(Severity.LOW)}) == "plan"
        assert _should_notify({"analysis": _make_analysis(Severity.MODERATE)}) == "plan"
        assert _should_notify({"analysis": _make_analysis(Severity.NOT_A_PROBLEM)}) == "end"


# ─── build_workflow ─────────────────────────────────────────────────────────


def test_build_workflow_returns_compiled_graph():
    mcp_manager = MagicMock()
    workflow = build_workflow(mcp_manager)
    # CompiledStateGraph has an invoke method
    assert hasattr(workflow, "invoke") or hasattr(workflow, "ainvoke")
