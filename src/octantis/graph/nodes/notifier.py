"""Notifier node: sends formatted alerts to Slack and Discord."""

import structlog

from octantis.config import settings
from octantis.graph.state import AgentState
from octantis.notifiers.discord import DiscordNotifier
from octantis.notifiers.slack import SlackNotifier

log = structlog.get_logger(__name__)


async def notifier_node(state: AgentState) -> AgentState:
    """Send notifications to configured channels."""
    event_id = state["enriched_event"].original.event_id
    analysis = state["analysis"]
    plan = state.get("action_plan")

    log.info("notifier.start", event_id=event_id, severity=analysis.severity)

    notifications_sent: list[str] = []

    if settings.slack.enabled:
        try:
            slack = SlackNotifier(
                webhook_url=settings.slack.webhook_url,
                bot_token=settings.slack.bot_token,
                channel=settings.slack.channel,
            )
            await slack.send(
                enriched_event=state["enriched_event"],
                analysis=analysis,
                action_plan=plan,
            )
            notifications_sent.append("slack")
            log.info("notifier.slack.sent", event_id=event_id)
        except Exception as exc:
            log.error("notifier.slack.error", event_id=event_id, error=str(exc))

    if settings.discord.enabled:
        try:
            discord = DiscordNotifier(webhook_url=settings.discord.webhook_url)
            await discord.send(
                enriched_event=state["enriched_event"],
                analysis=analysis,
                action_plan=plan,
            )
            notifications_sent.append("discord")
            log.info("notifier.discord.sent", event_id=event_id)
        except Exception as exc:
            log.error("notifier.discord.error", event_id=event_id, error=str(exc))

    log.info(
        "notifier.done",
        event_id=event_id,
        channels=notifications_sent,
    )

    return {**state, "notifications_sent": notifications_sent}
