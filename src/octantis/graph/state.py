# SPDX-License-Identifier: AGPL-3.0-or-later
"""LangGraph state definition for the Octantis workflow."""

from typing import TypedDict

from octantis.models import ActionPlan, InfraEvent, InvestigationResult, SeverityAnalysis


class AgentState(TypedDict, total=False):
    """Shared state passed between graph nodes."""

    # Input: raw event from OTLP receiver
    event: InfraEvent

    # After investigate node (MCP-driven investigation)
    investigation: InvestigationResult

    # After analyzer node
    analysis: SeverityAnalysis

    # After planner node (only if severity warrants it)
    action_plan: ActionPlan | None

    # Notification results
    notifications_sent: list[str]

    # Error tracking
    error: str | None
