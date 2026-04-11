"""Unit tests for notifier node and notifier implementations."""

from unittest.mock import AsyncMock, patch

import pytest

from octantis.graph.nodes.notifier import notifier_node
from octantis.models.action_plan import ActionPlan, ActionStep, StepType
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import InfraEvent, InvestigationResult, K8sResource
from octantis.notifiers.discord import _build_embed
from octantis.notifiers.slack import _build_blocks


def _make_state(severity: Severity = Severity.CRITICAL, mcp_degraded: bool = False):
    event = InfraEvent(
        event_id="notif-001",
        event_type="metric",
        source="api-server",
        resource=K8sResource(
            service_name="api-server",
            k8s_namespace="production",
        ),
    )
    investigation = InvestigationResult(
        original_event=event,
        evidence_summary="CPU at 95%, pod restarting",
        mcp_degraded=mcp_degraded,
    )
    analysis = SeverityAnalysis(
        severity=severity,
        confidence=0.9,
        reasoning="Service is down",
        affected_components=["api-server"],
        is_transient=False,
    )
    plan = ActionPlan(
        title="Restart crashed pods",
        summary="Pod is crash-looping, restart and investigate",
        steps=[
            ActionStep(
                order=1,
                type=StepType.INVESTIGATE,
                title="Check pod logs",
                description="Review recent logs for errors",
                command="kubectl logs api-server-abc -n production --tail=100",
                expected_outcome="Identify root cause",
            ),
            ActionStep(
                order=2,
                type=StepType.EXECUTE,
                title="Restart deployment",
                description="Rolling restart to clear bad state",
                command="kubectl rollout restart deployment/api-server -n production",
            ),
        ],
        escalate_to=["team-sre"],
        estimated_resolution_minutes=15,
    )
    return {"investigation": investigation, "analysis": analysis, "action_plan": plan}


@pytest.mark.asyncio
async def test_notifier_sends_to_slack_and_discord():
    """Notifier node sends to both Slack and Discord when both are enabled."""
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
        mock_settings.discord.webhook_url = "https://discord.com/test"

        MockSlack.return_value.send = AsyncMock()
        MockDiscord.return_value.send = AsyncMock()

        result = await notifier_node(state)

    assert "slack" in result["notifications_sent"]
    assert "discord" in result["notifications_sent"]


@pytest.mark.asyncio
async def test_notifier_slack_only():
    """Notifier only sends to Slack when Discord is disabled."""
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
        mock_settings.discord.enabled = False

        MockSlack.return_value.send = AsyncMock()

        result = await notifier_node(state)

    assert result["notifications_sent"] == ["slack"]
    MockDiscord.assert_not_called()


@pytest.mark.asyncio
async def test_notifier_continues_on_error():
    """Notifier continues to Discord if Slack fails."""
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
        mock_settings.discord.webhook_url = "https://discord.com/test"

        MockSlack.return_value.send = AsyncMock(side_effect=Exception("Slack down"))
        MockDiscord.return_value.send = AsyncMock()

        result = await notifier_node(state)

    assert "slack" not in result["notifications_sent"]
    assert "discord" in result["notifications_sent"]


def test_slack_blocks_structure():
    """Slack Block Kit output contains required sections."""
    state = _make_state()
    blocks = _build_blocks(state["investigation"], state["analysis"], state["action_plan"])
    assert any(b.get("type") == "header" for b in blocks)
    section_texts = [
        b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
    ]
    assert any("Service is down" in t for t in section_texts)


def test_discord_embed_structure():
    """Discord embed has required fields and correct color for CRITICAL."""
    state = _make_state(severity=Severity.CRITICAL)
    embed = _build_embed(state["investigation"], state["analysis"], state["action_plan"])
    assert embed["color"] == 0xFF0000
    assert "CRITICAL" in embed["title"]
    field_names = [f["name"] for f in embed["fields"]]
    assert "Service" in field_names
    assert "Analysis" in field_names
    assert "Action Plan" in field_names


def test_discord_embed_moderate_color():
    """Discord embed uses orange for MODERATE."""
    state = _make_state(severity=Severity.MODERATE)
    embed = _build_embed(state["investigation"], state["analysis"], None)
    assert embed["color"] == 0xFFA500


def test_slack_blocks_degradation_warning():
    """Slack blocks include MCP degradation warning when mcp_degraded is True."""
    state = _make_state(mcp_degraded=True)
    blocks = _build_blocks(
        state["investigation"],
        state["analysis"],
        state["action_plan"],
        extra_text=":warning: MCP servers unavailable",
    )
    section_texts = [
        b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
    ]
    assert any("MCP" in t for t in section_texts)


def test_discord_embed_degradation_warning():
    """Discord embed includes MCP degradation warning field."""
    state = _make_state(mcp_degraded=True)
    embed = _build_embed(
        state["investigation"],
        state["analysis"],
        None,
        extra_text="MCP servers unavailable",
    )
    field_names = [f["name"] for f in embed["fields"]]
    assert "Warning" in field_names
