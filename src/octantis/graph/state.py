"""LangGraph state definition for the Octantis workflow."""

from typing import TypedDict

from octantis.models import ActionPlan, EnrichedEvent, InfraEvent, SeverityAnalysis


class AgentState(TypedDict, total=False):
    """Shared state passed between graph nodes."""

    # Input: raw event from Redpanda
    event: InfraEvent

    # After collector node
    enriched_event: EnrichedEvent

    # After analyzer node
    analysis: SeverityAnalysis

    # After planner node (only if severity warrants it)
    action_plan: ActionPlan | None

    # Notification results
    notifications_sent: list[str]

    # Error tracking
    error: str | None
