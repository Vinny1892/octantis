"""Tests for built-in notifier plugin adapters (SlackNotifierPlugin, DiscordNotifierPlugin).

These tests exercise the SDK Protocol boundary — verifying that the adapter
correctly bridges SDK types to core notifier implementations.
"""

from unittest.mock import AsyncMock, patch

import pytest
from octantis_plugin_sdk import ActionPlan, InvestigationResult, SeverityAnalysis

from octantis.plugins.builtins.notifier_plugins import (
    DiscordNotifierPlugin,
    SlackNotifierPlugin,
    _to_core_result,
)


def _make_sdk_event(**overrides):
    from octantis_plugin_sdk import Event

    defaults = {
        "event_id": "test-001",
        "event_type": "metric",
        "source": "api-server",
        "resource": {
            "service.name": "api-server",
            "k8s.namespace.name": "production",
        },
        "metrics": [{"name": "cpu_usage", "value": 95.0}],
    }
    defaults.update(overrides)
    return Event(**defaults)


def _make_sdk_result(**overrides):
    defaults = {
        "event_id": "test-001",
        "original_event": _make_sdk_event(),
        "evidence_summary": "CPU at 95%",
    }
    defaults.update(overrides)
    return InvestigationResult(**defaults)


def _make_sdk_analysis(severity="CRITICAL"):
    from octantis_plugin_sdk.analysis import Severity

    return SeverityAnalysis(
        severity=Severity(severity),
        confidence=0.92,
        reasoning="Service is crashing due to OOM",
        affected_components=["api-server"],
    )


def _make_sdk_plan():
    from octantis_plugin_sdk.action_plan import ActionStep, StepType

    return ActionPlan(
        title="Fix OOM crash",
        summary="Increase memory limits",
        steps=[
            ActionStep(
                order=1,
                type=StepType.EXECUTE,
                title="Increase limits",
                description="Patch deployment",
            ),
        ],
        escalate_to=["team-sre"],
    )


# ─── _to_core_result ──────────────────────────────────────────────────────


def test_to_core_result_basic_fields():
    sdk_result = _make_sdk_result()
    core = _to_core_result(sdk_result)

    assert core.original_event.event_id == "test-001"
    assert core.original_event.source == "api-server"
    assert core.evidence_summary == "CPU at 95%"


def test_to_core_result_resource_extra():
    sdk_result = _make_sdk_result()
    core = _to_core_result(sdk_result)

    assert core.original_event.resource.extra["k8s.namespace.name"] == "production"


def test_to_core_result_service_name_from_resource():
    sdk_result = _make_sdk_result()
    core = _to_core_result(sdk_result)

    assert core.original_event.resource.service_name == "api-server"


def test_to_core_result_mcp_fields():
    sdk_result = _make_sdk_result(
        mcp_servers_used=["grafana"],
        mcp_degraded=True,
        budget_exhausted=True,
        investigation_duration_s=2.5,
        tokens_input=100,
        tokens_output=50,
    )
    core = _to_core_result(sdk_result)

    assert core.mcp_servers_used == ["grafana"]
    assert core.mcp_degraded is True
    assert core.budget_exhausted is True
    assert core.investigation_duration_s == 2.5
    assert core.tokens_input == 100
    assert core.tokens_output == 50


# ─── SlackNotifierPlugin ──────────────────────────────────────────────────


class TestSlackNotifierPlugin:
    def test_setup_with_webhook(self):
        plugin = SlackNotifierPlugin()
        plugin.setup({"webhook_url": "https://hooks.slack.com/test", "channel": "#alerts"})
        assert plugin._notifier is not None

    def test_setup_with_empty_config_creates_notifier(self):
        plugin = SlackNotifierPlugin()
        plugin.setup({})
        assert plugin._notifier is not None

    def test_teardown_clears_notifier(self):
        plugin = SlackNotifierPlugin()
        plugin.setup({"webhook_url": "https://hooks.slack.com/test"})
        plugin.teardown()
        assert plugin._notifier is None

    @pytest.mark.asyncio
    async def test_send_when_not_setup(self):
        plugin = SlackNotifierPlugin()
        plugin.setup({})
        result = _make_sdk_result()
        analysis = _make_sdk_analysis()
        await plugin.send(result, analysis)

    @pytest.mark.asyncio
    async def test_send_calls_core_notifier(self):
        plugin = SlackNotifierPlugin()
        plugin.setup({"webhook_url": "https://hooks.slack.com/test"})

        result = _make_sdk_result()
        analysis = _make_sdk_analysis()
        plan = _make_sdk_plan()

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        with patch("octantis.notifiers.slack.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await plugin.send(result, analysis, action_plan=plan, extra_text="degraded")

            mock_client.post.assert_called_once()
            payload = mock_client.post.call_args[1]["json"]
            assert "attachments" in payload


# ─── DiscordNotifierPlugin ────────────────────────────────────────────────


class TestDiscordNotifierPlugin:
    def test_setup_with_webhook(self):
        plugin = DiscordNotifierPlugin()
        plugin.setup({"webhook_url": "https://discord.com/api/webhooks/test"})
        assert plugin._notifier is not None

    def test_setup_without_webhook(self):
        plugin = DiscordNotifierPlugin()
        plugin.setup({})
        assert plugin._notifier is None

    def test_teardown_clears_notifier(self):
        plugin = DiscordNotifierPlugin()
        plugin.setup({"webhook_url": "https://discord.com/api/webhooks/test"})
        plugin.teardown()
        assert plugin._notifier is None

    @pytest.mark.asyncio
    async def test_send_when_not_setup(self):
        plugin = DiscordNotifierPlugin()
        plugin.setup({})
        result = _make_sdk_result()
        analysis = _make_sdk_analysis()
        await plugin.send(result, analysis)

    @pytest.mark.asyncio
    async def test_send_calls_core_notifier(self):
        plugin = DiscordNotifierPlugin()
        plugin.setup({"webhook_url": "https://discord.com/api/webhooks/test"})

        result = _make_sdk_result()
        analysis = _make_sdk_analysis()

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        with patch("octantis.notifiers.discord.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await plugin.send(result, analysis)

            mock_client.post.assert_called_once()
            payload = mock_client.post.call_args[1]["json"]
            assert "embeds" in payload
