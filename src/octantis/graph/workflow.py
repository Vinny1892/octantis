# SPDX-License-Identifier: AGPL-3.0-or-later
"""LangGraph workflow definition for Octantis."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import structlog
from langgraph.graph import END, START, StateGraph

from octantis.config import settings
from octantis.graph.nodes import (
    analyzer_node,
    investigate_node,
    notifier_node,
    planner_node,
)
from octantis.graph.state import AgentState
from octantis.models.analysis import Severity

if TYPE_CHECKING:
    from octantis.mcp_client import MCPClientManager

log = structlog.get_logger(__name__)

# Severity ordering for threshold comparison
_SEVERITY_ORDER = {
    Severity.NOT_A_PROBLEM: 0,
    Severity.LOW: 1,
    Severity.MODERATE: 2,
    Severity.CRITICAL: 3,
}

_NOTIFY_THRESHOLD = {
    "NOT_A_PROBLEM": Severity.NOT_A_PROBLEM,
    "LOW": Severity.LOW,
    "MODERATE": Severity.MODERATE,
    "CRITICAL": Severity.CRITICAL,
}


def _should_notify(state: AgentState) -> str:
    """Conditional edge: route to planner or end based on severity."""
    analysis = state.get("analysis")
    if not analysis:
        log.warning("workflow.no_analysis_found")
        return "end"

    threshold = _NOTIFY_THRESHOLD.get(settings.min_severity_to_notify, Severity.MODERATE)
    severity_value = _SEVERITY_ORDER.get(analysis.severity, 0)
    threshold_value = _SEVERITY_ORDER.get(threshold, 2)

    if severity_value >= threshold_value:
        log.info(
            "workflow.routing_to_planner",
            severity=analysis.severity,
            threshold=settings.min_severity_to_notify,
        )
        return "plan"
    else:
        log.info(
            "workflow.routing_to_end",
            severity=analysis.severity,
            reasoning=analysis.reasoning[:100],
        )
        return "end"


def build_workflow(mcp_manager: MCPClientManager) -> StateGraph:
    """Build and compile the LangGraph workflow.

    Args:
        mcp_manager: The MCP client manager providing tools for investigation.
    """
    graph = StateGraph(AgentState)

    # Bind mcp_manager to investigate_node
    bound_investigate = partial(investigate_node, mcp_manager=mcp_manager)

    # Add nodes
    graph.add_node("investigate", bound_investigate)
    graph.add_node("analyze", analyzer_node)
    graph.add_node("plan", planner_node)
    graph.add_node("notify", notifier_node)

    # Edges: investigate → analyze → conditional → plan → notify → END
    graph.add_edge(START, "investigate")
    graph.add_edge("investigate", "analyze")
    graph.add_conditional_edges(
        "analyze",
        _should_notify,
        {
            "plan": "plan",
            "end": END,
        },
    )
    graph.add_edge("plan", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
