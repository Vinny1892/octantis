"""Unit tests for Slack notifier — _build_blocks and SlackNotifier."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.models.action_plan import ActionPlan, ActionStep, StepType
from octantis.models.analysis import Severity, SeverityAnalysis
from octantis.models.event import (
    InfraEvent,
    InvestigationResult,
    K8sResource,
    MCPQueryRecord,
    MetricDataPoint,
)
from octantis.notifiers.slack import SlackNotifier, _build_blocks


def _make_investigation(**kwargs) -> InvestigationResult:
    event = InfraEvent(
        event_id="slack-001",
        event_type="metric",
        source="api-server",
        resource=K8sResource(
            service_name="api-server",
            k8s_namespace="production",
            k8s_pod_name="api-abc",
        ),
        metrics=[MetricDataPoint(name="cpu_usage", value=95.0)],
    )
    defaults = {
        "original_event": event,
        "evidence_summary": "CPU at 95%",
    }
    defaults.update(kwargs)
    return InvestigationResult(**defaults)


def _make_analysis(severity=Severity.CRITICAL) -> SeverityAnalysis:
    return SeverityAnalysis(
        severity=severity,
        confidence=0.92,
        reasoning="Service is crashing due to OOM",
        affected_components=["api-server", "database"],
    )


def _make_plan() -> ActionPlan:
    return ActionPlan(
        title="Fix OOM crash",
        summary="Increase memory limits",
        steps=[
            ActionStep(
                order=1,
                type=StepType.INVESTIGATE,
                title="Check memory",
                description="Review container memory metrics",
            ),
            ActionStep(
                order=2,
                type=StepType.EXECUTE,
                title="Increase limits",
                description="Patch deployment",
                command="kubectl set resources deployment/api-server --limits=memory=1Gi",
            ),
        ],
        escalate_to=["team-sre"],
    )


# ─── _build_blocks ────────────────────────────────────────────────────────


def test_build_blocks_basic():
    inv = _make_investigation()
    analysis = _make_analysis()
    blocks = _build_blocks(inv, analysis, plan=None)

    # Header block
    assert blocks[0]["type"] == "header"
    assert "CRITICAL" in blocks[0]["text"]["text"]
    assert "api-server" in blocks[0]["text"]["text"]

    # Has divider
    assert any(b["type"] == "divider" for b in blocks)

    # Context footer
    assert blocks[-1]["type"] == "context"
    assert "slack-001" in blocks[-1]["elements"][0]["text"]


def test_build_blocks_with_affected_components():
    inv = _make_investigation()
    analysis = _make_analysis()
    blocks = _build_blocks(inv, analysis, plan=None)

    texts = [b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section"]
    assert any("api-server, database" in t for t in texts)


def test_build_blocks_with_queries():
    inv = _make_investigation(
        queries_executed=[
            MCPQueryRecord(
                tool_name="query_prometheus",
                query="rate(http_500[5m])",
                result_summary="0.05",
                duration_ms=120.0,
                datasource="promql",
            ),
        ],
        investigation_duration_s=1.5,
    )
    analysis = _make_analysis()
    blocks = _build_blocks(inv, analysis, plan=None)

    texts = [b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section"]
    assert any("1 MCP queries" in t for t in texts)


def test_build_blocks_with_plan():
    inv = _make_investigation()
    analysis = _make_analysis()
    plan = _make_plan()
    blocks = _build_blocks(inv, analysis, plan=plan)

    texts = [b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section"]
    assert any("Fix OOM crash" in t for t in texts)
    assert any("Increase limits" in t for t in texts)
    assert any("team-sre" in t for t in texts)


def test_build_blocks_with_extra_text():
    inv = _make_investigation()
    analysis = _make_analysis()
    blocks = _build_blocks(inv, analysis, plan=None, extra_text="MCP degraded warning")

    texts = [b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section"]
    assert any("MCP degraded warning" in t for t in texts)


def test_build_blocks_severity_emoji():
    inv = _make_investigation()
    for sev, emoji in [
        (Severity.CRITICAL, ":red_circle:"),
        (Severity.LOW, ":yellow_circle:"),
        (Severity.NOT_A_PROBLEM, ":white_check_mark:"),
    ]:
        analysis = _make_analysis(severity=sev)
        blocks = _build_blocks(inv, analysis, plan=None)
        assert emoji in blocks[0]["text"]["text"]


# ─── SlackNotifier ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_send_webhook():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    inv = _make_investigation()
    analysis = _make_analysis()

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None

    with patch("octantis.notifiers.slack.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notifier.send(inv, analysis)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://hooks.slack.com/test"
        payload = call_args[1]["json"]
        assert "attachments" in payload
        assert payload["attachments"][0]["color"] == "#FF0000"


@pytest.mark.asyncio
async def test_slack_send_api_bot_token():
    notifier = SlackNotifier(bot_token="xoxb-test-token", channel="#alerts")
    inv = _make_investigation()
    analysis = _make_analysis()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"ok": True}

    with patch("octantis.notifiers.slack.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notifier.send(inv, analysis)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "chat.postMessage" in call_args[0][0]
        assert "Bearer xoxb-test-token" in call_args[1]["headers"]["Authorization"]
        payload = call_args[1]["json"]
        assert payload["channel"] == "#alerts"


@pytest.mark.asyncio
async def test_slack_send_api_error_raises():
    notifier = SlackNotifier(bot_token="xoxb-test")
    inv = _make_investigation()
    analysis = _make_analysis()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"ok": False, "error": "channel_not_found"}

    with patch("octantis.notifiers.slack.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="channel_not_found"):
            await notifier.send(inv, analysis)


@pytest.mark.asyncio
async def test_slack_send_no_config_does_nothing():
    """When neither webhook nor bot_token is set, send is a no-op."""
    notifier = SlackNotifier()
    inv = _make_investigation()
    analysis = _make_analysis()

    with patch("octantis.notifiers.slack.httpx.AsyncClient") as mock_client_cls:
        await notifier.send(inv, analysis)
        mock_client_cls.assert_not_called()
