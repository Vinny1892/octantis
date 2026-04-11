"""Unit tests for graph/nodes/notifier.py — notifier_node."""

from unittest.mock import AsyncMock, patch

import pytest

from octantis.graph.nodes.notifier import notifier_node
from octantis.models.action_plan import ActionPlan, ActionStep, StepType
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import (
    InfraEvent,
    InvestigationResult,
    K8sResource,
    MetricDataPoint,
)


def _make_state(mcp_degraded=False, with_plan=False):
    event = InfraEvent(
        event_id="notify-001",
        event_type="metric",
        source="api-server",
        resource=K8sResource(service_name="api-server", k8s_namespace="prod"),
        metrics=[MetricDataPoint(name="cpu_usage", value=95.0)],
    )
    investigation = InvestigationResult(
        original_event=event,
        evidence_summary="CPU spike",
        mcp_degraded=mcp_degraded,
    )
    analysis = SeverityAnalysis(
        severity=Severity.CRITICAL,
        confidence=0.9,
        reasoning="OOM crash",
        affected_components=["api-server"],
    )
    state = {"investigation": investigation, "analysis": analysis}
    if with_plan:
        state["action_plan"] = ActionPlan(
            title="Fix",
            summary="Fix it",
            steps=[
                ActionStep(
                    order=1,
                    type=StepType.INVESTIGATE,
                    title="Check",
                    description="Check it",
                )
            ],
        )
    return state


@pytest.mark.asyncio
async def test_notifier_sends_slack():
    state = _make_state()

    with (
        patch("octantis.graph.nodes.notifier.settings") as mock_settings,
        patch("octantis.graph.nodes.notifier.SlackNotifier") as MockSlack,
        patch("octantis.graph.nodes.notifier.DiscordNotifier"),
    ):
        mock_settings.slack.enabled = True
        mock_settings.slack.webhook_url = "https://hooks.slack.com/test"
        mock_settings.slack.bot_token = None
        mock_settings.slack.channel = "#alerts"
        mock_settings.discord.enabled = False

        mock_slack_inst = AsyncMock()
        MockSlack.return_value = mock_slack_inst

        result = await notifier_node(state)

    assert "slack" in result["notifications_sent"]
    mock_slack_inst.send.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_sends_discord():
    state = _make_state()

    with (
        patch("octantis.graph.nodes.notifier.settings") as mock_settings,
        patch("octantis.graph.nodes.notifier.SlackNotifier"),
        patch("octantis.graph.nodes.notifier.DiscordNotifier") as MockDiscord,
    ):
        mock_settings.slack.enabled = False
        mock_settings.discord.enabled = True
        mock_settings.discord.webhook_url = "https://discord.com/api/webhooks/test"

        mock_discord_inst = AsyncMock()
        MockDiscord.return_value = mock_discord_inst

        result = await notifier_node(state)

    assert "discord" in result["notifications_sent"]
    mock_discord_inst.send.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_sends_both():
    state = _make_state()

    with (
        patch("octantis.graph.nodes.notifier.settings") as mock_settings,
        patch("octantis.graph.nodes.notifier.SlackNotifier") as MockSlack,
        patch("octantis.graph.nodes.notifier.DiscordNotifier") as MockDiscord,
    ):
        mock_settings.slack.enabled = True
        mock_settings.slack.webhook_url = "https://hooks.slack.com/test"
        mock_settings.slack.bot_token = None
        mock_settings.slack.channel = "#alerts"
        mock_settings.discord.enabled = True
        mock_settings.discord.webhook_url = "https://discord.com/api/webhooks/test"

        MockSlack.return_value = AsyncMock()
        MockDiscord.return_value = AsyncMock()

        result = await notifier_node(state)

    assert "slack" in result["notifications_sent"]
    assert "discord" in result["notifications_sent"]


@pytest.mark.asyncio
async def test_notifier_no_channels():
    state = _make_state()

    with patch("octantis.graph.nodes.notifier.settings") as mock_settings:
        mock_settings.slack.enabled = False
        mock_settings.discord.enabled = False

        result = await notifier_node(state)

    assert result["notifications_sent"] == []


@pytest.mark.asyncio
async def test_notifier_slack_error_doesnt_crash():
    state = _make_state()

    with (
        patch("octantis.graph.nodes.notifier.settings") as mock_settings,
        patch("octantis.graph.nodes.notifier.SlackNotifier") as MockSlack,
    ):
        mock_settings.slack.enabled = True
        mock_settings.slack.webhook_url = "https://hooks.slack.com/test"
        mock_settings.slack.bot_token = None
        mock_settings.slack.channel = "#alerts"
        mock_settings.discord.enabled = False

        mock_slack_inst = AsyncMock()
        mock_slack_inst.send.side_effect = RuntimeError("Slack down")
        MockSlack.return_value = mock_slack_inst

        result = await notifier_node(state)

    assert "slack" not in result["notifications_sent"]


@pytest.mark.asyncio
async def test_notifier_mcp_degraded_adds_warning():
    state = _make_state(mcp_degraded=True)

    with (
        patch("octantis.graph.nodes.notifier.settings") as mock_settings,
        patch("octantis.graph.nodes.notifier.SlackNotifier") as MockSlack,
    ):
        mock_settings.slack.enabled = True
        mock_settings.slack.webhook_url = "https://hooks.slack.com/test"
        mock_settings.slack.bot_token = None
        mock_settings.slack.channel = "#alerts"
        mock_settings.discord.enabled = False

        mock_slack_inst = AsyncMock()
        MockSlack.return_value = mock_slack_inst

        await notifier_node(state)

    call_kwargs = mock_slack_inst.send.call_args[1]
    assert "MCP Degradation Warning" in call_kwargs["extra_text"]
