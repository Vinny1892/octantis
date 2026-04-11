"""Discord notifier using webhook embeds."""

from typing import Any

import httpx
import structlog

from octantis.models.action_plan import ActionPlan
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import InvestigationResult

log = structlog.get_logger(__name__)


def _build_embed(
    investigation: InvestigationResult,
    analysis: SeverityAnalysis,
    plan: ActionPlan | None,
    extra_text: str = "",
) -> dict[str, Any]:
    event = investigation.original_event
    svc = event.resource.service_name or "unknown"
    context = event.resource.context_summary()

    fields: list[dict[str, Any]] = [
        {"name": "Service", "value": svc, "inline": True},
        {"name": "Context", "value": context[:200], "inline": True},
        {
            "name": "Severity",
            "value": f"{analysis.severity} ({analysis.confidence:.0%})",
            "inline": True,
        },
        {
            "name": "Transient",
            "value": "Yes" if analysis.is_transient else "No",
            "inline": True,
        },
        {"name": "Analysis", "value": analysis.reasoning[:1024], "inline": False},
    ]

    if analysis.affected_components:
        fields.append(
            {
                "name": "Affected Components",
                "value": ", ".join(analysis.affected_components[:10]),
                "inline": False,
            }
        )

    # Investigation context
    if investigation.queries_executed:
        queries_count = len(investigation.queries_executed)
        duration = investigation.investigation_duration_s
        fields.append(
            {
                "name": "Investigation",
                "value": f"{queries_count} MCP queries in {duration:.1f}s",
                "inline": False,
            }
        )

    if plan:
        plan_lines = [f"**{plan.title}**", plan.summary, ""]
        for step in plan.steps[:4]:
            plan_lines.append(f"`{step.order}.` **[{step.type.value.upper()}]** {step.title}")
            if step.command:
                plan_lines.append(f"```{step.command}```")
        fields.append(
            {
                "name": "Action Plan",
                "value": "\n".join(plan_lines)[:1024],
                "inline": False,
            }
        )
        if plan.escalate_to:
            fields.append(
                {
                    "name": "Escalate To",
                    "value": ", ".join(plan.escalate_to),
                    "inline": False,
                }
            )

    # MCP degradation warning
    if extra_text:
        fields.append(
            {
                "name": "Warning",
                "value": extra_text.strip()[:1024],
                "inline": False,
            }
        )

    title_emoji = {
        Severity.CRITICAL: "\U0001f534",
        Severity.MODERATE: "\U0001f7e0",
        Severity.LOW: "\U0001f7e1",
        Severity.NOT_A_PROBLEM: "\u2705",
    }[analysis.severity]

    return {
        "title": f"{title_emoji} [{analysis.severity}] Infrastructure Alert \u2014 {svc}",
        "color": analysis.severity.discord_color,
        "fields": fields,
        "footer": {"text": f"Event ID: {event.event_id} | Octantis"},
    }


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(
        self,
        investigation: InvestigationResult,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
        extra_text: str = "",
    ) -> None:
        embed = _build_embed(investigation, analysis, action_plan, extra_text)
        payload = {"embeds": [embed]}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self._webhook_url, json=payload)
            resp.raise_for_status()
