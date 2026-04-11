"""Unit tests for Discord notifier — _build_embed and DiscordNotifier."""

from unittest.mock import AsyncMock, patch

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
from octantis.notifiers.discord import DiscordNotifier, _build_embed


def _make_investigation(**kwargs) -> InvestigationResult:
    event = InfraEvent(
        event_id="discord-001",
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


# ─── _build_embed ─────────────────────────────────────────────────────────


def test_build_embed_basic():
    inv = _make_investigation()
    analysis = _make_analysis()
    embed = _build_embed(inv, analysis, plan=None)

    assert "CRITICAL" in embed["title"]
    assert "api-server" in embed["title"]
    assert embed["color"] == Severity.CRITICAL.discord_color
    assert embed["footer"]["text"].startswith("Event ID: discord-001")

    field_names = [f["name"] for f in embed["fields"]]
    assert "Service" in field_names
    assert "Severity" in field_names
    assert "Analysis" in field_names
    assert "Transient" in field_names


def test_build_embed_affected_components():
    inv = _make_investigation()
    analysis = _make_analysis()
    embed = _build_embed(inv, analysis, plan=None)

    comp_field = next(f for f in embed["fields"] if f["name"] == "Affected Components")
    assert "api-server" in comp_field["value"]
    assert "database" in comp_field["value"]


def test_build_embed_no_affected_components():
    inv = _make_investigation()
    analysis = SeverityAnalysis(
        severity=Severity.LOW,
        confidence=0.5,
        reasoning="Minor issue",
        affected_components=[],
    )
    embed = _build_embed(inv, analysis, plan=None)
    field_names = [f["name"] for f in embed["fields"]]
    assert "Affected Components" not in field_names


def test_build_embed_with_queries():
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
    embed = _build_embed(inv, analysis, plan=None)

    inv_field = next(f for f in embed["fields"] if f["name"] == "Investigation")
    assert "1 MCP queries" in inv_field["value"]


def test_build_embed_with_plan():
    inv = _make_investigation()
    analysis = _make_analysis()
    plan = _make_plan()
    embed = _build_embed(inv, analysis, plan=plan)

    field_names = [f["name"] for f in embed["fields"]]
    assert "Action Plan" in field_names
    assert "Escalate To" in field_names

    plan_field = next(f for f in embed["fields"] if f["name"] == "Action Plan")
    assert "Fix OOM crash" in plan_field["value"]

    esc_field = next(f for f in embed["fields"] if f["name"] == "Escalate To")
    assert "team-sre" in esc_field["value"]


def test_build_embed_with_extra_text():
    inv = _make_investigation()
    analysis = _make_analysis()
    embed = _build_embed(inv, analysis, plan=None, extra_text="MCP degraded")

    warn_field = next(f for f in embed["fields"] if f["name"] == "Warning")
    assert "MCP degraded" in warn_field["value"]


def test_build_embed_severity_colors():
    inv = _make_investigation()
    for sev in Severity:
        analysis = _make_analysis(severity=sev)
        embed = _build_embed(inv, analysis, plan=None)
        assert embed["color"] == sev.discord_color


# ─── DiscordNotifier.send ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discord_send():
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test")
    inv = _make_investigation()
    analysis = _make_analysis()

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None

    with patch("octantis.notifiers.discord.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notifier.send(inv, analysis)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://discord.com/api/webhooks/test"
        payload = call_args[1]["json"]
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1


@pytest.mark.asyncio
async def test_discord_send_with_plan():
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test")
    inv = _make_investigation()
    analysis = _make_analysis()
    plan = _make_plan()

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None

    with patch("octantis.notifiers.discord.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notifier.send(inv, analysis, action_plan=plan)

        payload = mock_client.post.call_args[1]["json"]
        embed = payload["embeds"][0]
        field_names = [f["name"] for f in embed["fields"]]
        assert "Action Plan" in field_names
