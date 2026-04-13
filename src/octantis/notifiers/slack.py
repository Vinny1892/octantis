# SPDX-License-Identifier: AGPL-3.0-or-later
"""Slack notifier using Block Kit."""

from typing import Any

import httpx
import structlog

from octantis.models.action_plan import ActionPlan
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import InvestigationResult

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
    investigation: InvestigationResult,
    analysis: SeverityAnalysis,
    plan: ActionPlan | None,
    extra_text: str = "",
) -> list[dict[str, Any]]:
    event = investigation.original_event
    svc = event.resource.service_name or "unknown"
    context = event.resource.context_summary()
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
                {"type": "mrkdwn", "text": f"*Context:*\n{context[:200]}"},
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

    # Investigation context
    if investigation.queries_executed:
        queries_count = len(investigation.queries_executed)
        duration = investigation.investigation_duration_s
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Investigation:* {queries_count} MCP queries in {duration:.1f}s",
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
        for step in plan.steps[:5]:
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

    # MCP degradation warning
    if extra_text:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": extra_text.strip()},
            }
        )

    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Event ID: `{event.event_id}` | Source: {event.source} | Octantis",
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
        investigation: InvestigationResult,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
        extra_text: str = "",
    ) -> None:
        blocks = _build_blocks(investigation, analysis, action_plan, extra_text)
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
