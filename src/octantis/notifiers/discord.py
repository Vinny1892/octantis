"""Discord notifier using webhook embeds."""

from typing import Any

import httpx
import structlog

from octantis.models.action_plan import ActionPlan
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import EnrichedEvent

log = structlog.get_logger(__name__)


def _build_embed(
    enriched: EnrichedEvent,
    analysis: SeverityAnalysis,
    plan: ActionPlan | None,
) -> dict[str, Any]:
    svc = enriched.original.resource.service_name or "unknown"
    ns = enriched.original.resource.k8s_namespace or "unknown"

    fields: list[dict[str, Any]] = [
        {"name": "Service", "value": svc, "inline": True},
        {"name": "Namespace", "value": ns, "inline": True},
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

    prom = enriched.prometheus
    metric_parts = []
    if prom.cpu_usage_percent is not None:
        metric_parts.append(f"CPU: {prom.cpu_usage_percent:.1f}%")
    if prom.memory_usage_percent is not None:
        metric_parts.append(f"Mem: {prom.memory_usage_percent:.1f}%")
    if prom.error_rate_5m is not None:
        metric_parts.append(f"ErrRate: {prom.error_rate_5m:.3f}")
    if metric_parts:
        fields.append(
            {
                "name": "Metrics",
                "value": " | ".join(metric_parts),
                "inline": False,
            }
        )

    if plan:
        plan_lines = [f"**{plan.title}**", plan.summary, ""]
        for step in plan.steps[:4]:
            plan_lines.append(
                f"`{step.order}.` **[{step.type.value.upper()}]** {step.title}"
            )
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

    title_emoji = {
        Severity.CRITICAL: "🔴",
        Severity.MODERATE: "🟠",
        Severity.LOW: "🟡",
        Severity.NOT_A_PROBLEM: "✅",
    }[analysis.severity]

    return {
        "title": f"{title_emoji} [{analysis.severity}] Infrastructure Alert — {svc}",
        "color": analysis.severity.discord_color,
        "fields": fields,
        "footer": {
            "text": f"Event ID: {enriched.original.event_id} | Octantis"
        },
    }


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(
        self,
        enriched_event: EnrichedEvent,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
    ) -> None:
        embed = _build_embed(enriched_event, analysis, action_plan)
        payload = {"embeds": [embed]}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self._webhook_url, json=payload)
            resp.raise_for_status()
