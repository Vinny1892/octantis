"""Built-in notifier plugin adapters (Slack, Discord).

Each adapter wraps the existing notifier class (unchanged) and exposes it
through the SDK `Notifier` Protocol. The adapter owns the SDK→core bridge
for the `InvestigationResult` payload so the internal notifier code keeps
operating on rich core types.
"""

from __future__ import annotations

from typing import Any

from octantis_plugin_sdk import ActionPlan, InvestigationResult, SeverityAnalysis

from octantis.models.event import InfraEvent
from octantis.models.event import InvestigationResult as CoreInvestigationResult
from octantis.notifiers.discord import DiscordNotifier
from octantis.notifiers.slack import SlackNotifier


def _to_core_result(result: InvestigationResult) -> CoreInvestigationResult:
    """Convert the SDK InvestigationResult into core's rich InvestigationResult.

    The existing Slack/Discord notifier code calls `.resource.service_name`,
    `.resource.context_summary()`, and other typed-resource helpers, so we
    re-hydrate the core InfraEvent from the SDK dict fields.
    """
    sdk_event = result.original_event
    # Best-effort resource reconstruction: pass the raw dict as `extra` so
    # downstream helpers that read OTel attributes via `extra` still work.
    # Platform-specific typed fields stay on the original core-side pipeline
    # path; this adapter is only the Notifier boundary.
    core_event = InfraEvent(
        event_id=sdk_event.event_id,
        event_type=sdk_event.event_type,
        source=sdk_event.source,
        # resource is kept as default OTelResource — notifiers call
        # context_summary() which handles unknown attrs gracefully.
    )
    # Inject resource attributes as `extra` so context_summary sees them.
    core_event.resource.extra = dict(sdk_event.resource)
    core_event.resource.service_name = (
        sdk_event.resource.get("service.name")
        or sdk_event.resource.get("service_name")
    )

    return CoreInvestigationResult(
        original_event=core_event,
        queries_executed=[],
        evidence_summary=result.evidence_summary,
        mcp_servers_used=list(result.mcp_servers_used),
        mcp_degraded=result.mcp_degraded,
        budget_exhausted=result.budget_exhausted,
        investigation_duration_s=result.investigation_duration_s,
        tokens_input=result.tokens_input,
        tokens_output=result.tokens_output,
    )


class SlackNotifierPlugin:
    """Notifier plugin: Slack via webhook or bot API."""

    name = "slack"

    def __init__(self) -> None:
        self._notifier: SlackNotifier | None = None

    def setup(self, config: dict[str, Any]) -> None:
        self._notifier = SlackNotifier(
            webhook_url=config.get("webhook_url"),
            bot_token=config.get("bot_token"),
            channel=config.get("channel", "#infra-alerts"),
        )

    def teardown(self) -> None:
        self._notifier = None

    async def send(
        self,
        result: InvestigationResult,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
        extra_text: str = "",
    ) -> None:
        if self._notifier is None:
            return
        core_result = _to_core_result(result)
        await self._notifier.send(core_result, analysis, action_plan, extra_text)


class DiscordNotifierPlugin:
    """Notifier plugin: Discord via webhook."""

    name = "discord"

    def __init__(self) -> None:
        self._notifier: DiscordNotifier | None = None

    def setup(self, config: dict[str, Any]) -> None:
        url = config.get("webhook_url")
        if not url:
            self._notifier = None
            return
        self._notifier = DiscordNotifier(webhook_url=url)

    def teardown(self) -> None:
        self._notifier = None

    async def send(
        self,
        result: InvestigationResult,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
        extra_text: str = "",
    ) -> None:
        if self._notifier is None:
            return
        core_result = _to_core_result(result)
        await self._notifier.send(core_result, analysis, action_plan, extra_text)
