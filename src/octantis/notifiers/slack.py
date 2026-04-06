"""Slack notifier using Block Kit."""

from typing import Any

import httpx
import structlog

from octantis.models.action_plan import ActionPlan
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import EnrichedEvent

log = structlog.get_logger(__name__)

_SEVERITY_COLORS = {
    Severity.CRITICAL: "#FF0000",
    Severity.MODERATE: "#FFA500",
    Severity.LOW: "#FFFF00",
    Severity.NOT_A_PROBLEM: "#36a64f",
}

_SEVERITY_EMOJI = {
    Severity.CRITICAL: ":red_circle:",
    Severity.MODERATE: ":large_orange_circle:",
    Severity.LOW: ":yellow_circle:",
    Severity.NOT_A_PROBLEM: ":white_check_mark:",
}


def _build_blocks(
    enriched: EnrichedEvent,
    analysis: SeverityAnalysis,
    plan: ActionPlan | None,
) -> list[dict[str, Any]]:
    svc = enriched.original.resource.service_name or "unknown"
    ns = enriched.original.resource.k8s_namespace or "unknown"
    emoji = _SEVERITY_EMOJI[analysis.severity]

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} [{analysis.severity}] Infrastructure Alert - {svc}",
                "emoji": True,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n{svc}"},
                {"type": "mrkdwn", "text": f"*Namespace:*\n{ns}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Severity:*\n{analysis.severity} ({analysis.confidence:.0%} confidence)",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Transient:*\n{'Yes' if analysis.is_transient else 'No'}",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Analysis:*\n{analysis.reasoning}",
            },
        },
    ]

    if analysis.affected_components:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Affected components:*\n{', '.join(analysis.affected_components)}",
                },
            }
        )

    # Metrics context
    prom = enriched.prometheus
    metric_lines = []
    if prom.cpu_usage_percent is not None:
        metric_lines.append(f"CPU: {prom.cpu_usage_percent:.1f}%")
    if prom.memory_usage_percent is not None:
        metric_lines.append(f"Memory: {prom.memory_usage_percent:.1f}%")
    if prom.error_rate_5m is not None:
        metric_lines.append(f"Error rate (5m): {prom.error_rate_5m:.3f} req/s")
    if prom.request_latency_p99_ms is not None:
        metric_lines.append(f"P99 latency: {prom.request_latency_p99_ms:.0f}ms")

    if metric_lines:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Metrics:*\n" + " | ".join(metric_lines),
                },
            }
        )

    if plan:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Action Plan: {plan.title}*\n_{plan.summary}_",
                },
            }
        )
        for step in plan.steps[:5]:  # limit to 5 steps for readability
            step_text = (
                f"*{step.order}. [{step.type.value.upper()}] {step.title}*\n{step.description}"
            )
            if step.command:
                step_text += f"\n```{step.command}```"
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": step_text},
                }
            )

        if plan.escalate_to:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":telephone_receiver: *Escalate to:* {', '.join(plan.escalate_to)}",
                    },
                }
            )

    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Event ID: `{enriched.original.event_id}` | Source: {enriched.original.source} | Octantis",
                }
            ],
        }
    )

    return blocks


class SlackNotifier:
    def __init__(
        self,
        webhook_url: str | None = None,
        bot_token: str | None = None,
        channel: str = "#infra-alerts",
    ) -> None:
        self._webhook_url = webhook_url
        self._bot_token = bot_token
        self._channel = channel

    async def send(
        self,
        enriched_event: EnrichedEvent,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
    ) -> None:
        blocks = _build_blocks(enriched_event, analysis, action_plan)
        color = _SEVERITY_COLORS[analysis.severity]

        if self._webhook_url:
            await self._send_webhook(blocks, color)
        elif self._bot_token:
            await self._send_api(blocks, color)

    async def _send_webhook(self, blocks: list[dict], color: str) -> None:
        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ]
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self._webhook_url, json=payload)
            resp.raise_for_status()

    async def _send_api(self, blocks: list[dict], color: str) -> None:
        payload = {
            "channel": self._channel,
            "attachments": [{"color": color, "blocks": blocks}],
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                json=payload,
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack API error: {data.get('error')}")
