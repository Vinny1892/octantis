"""Built-in `trigger-filter` plugin adapter.

Wraps `octantis.pipeline.trigger_filter.TriggerFilter` in the SDK `Processor`
Protocol. The full refactor of the rule engine happens in Phase 2; this
adapter exists so Phase 1 has a real end-to-end smoke through the registry.
"""

from __future__ import annotations

from typing import Any

from octantis_plugin_sdk import Event

from octantis.models.event import InfraEvent
from octantis.pipeline.trigger_filter import Decision, TriggerFilter


class TriggerFilterPlugin:
    """Processor plugin: drops events that fail the trigger filter rules."""

    name = "trigger-filter"
    priority = 100

    def __init__(self) -> None:
        self._filter: TriggerFilter | None = None

    def setup(self, config: dict[str, Any]) -> None:
        self._filter = TriggerFilter.default(
            cpu_threshold=config.get("cpu_threshold", 75.0),
            memory_threshold=config.get("memory_threshold", 80.0),
            error_rate_threshold=config.get("error_rate_threshold", 0.01),
            benign_patterns=config.get("benign_patterns"),
        )

    def teardown(self) -> None:
        self._filter = None

    async def process(self, event: Event) -> Event | None:
        if self._filter is None:
            return event
        infra = InfraEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            source=event.source,
            metrics=[],
            logs=[],
        )
        result = self._filter.evaluate(infra)
        return event if result.decision is Decision.PASS else None
