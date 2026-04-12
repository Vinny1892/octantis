"""Built-in `fingerprint-cooldown` plugin adapter.

Wraps `octantis.pipeline.cooldown.FingerprintCooldown` in the SDK `Processor`
Protocol. Suppresses duplicate events within a sliding window.
"""

from __future__ import annotations

from typing import Any

from octantis_plugin_sdk import Event

from octantis.models.event import InfraEvent, OTelResource
from octantis.pipeline.cooldown import FingerprintCooldown


class FingerprintCooldownPlugin:
    """Processor plugin: drops events whose fingerprint is within the cooldown window."""

    name = "fingerprint-cooldown"
    priority = 200

    def __init__(self) -> None:
        self._cooldown: FingerprintCooldown | None = None

    def setup(self, config: dict[str, Any]) -> None:
        self._cooldown = FingerprintCooldown(
            cooldown_seconds=config.get("cooldown_seconds", 300.0),
            max_entries=config.get("max_entries", 1000),
        )

    def teardown(self) -> None:
        self._cooldown = None

    async def process(self, event: Event) -> Event | None:
        if self._cooldown is None:
            return event
        # The cooldown inspects resource.extra + metric names + log body.
        # We reconstruct a minimal InfraEvent sufficient for fingerprinting.
        infra = InfraEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            source=event.source,
            resource=OTelResource(extra=event.resource),
            metrics=[],
            logs=[],
        )
        return event if self._cooldown.should_investigate(infra) else None

    def stats(self) -> dict[str, Any]:
        """Expose the cooldown stats for observability. Not part of the Protocol."""
        if self._cooldown is None:
            return {"tracked_fingerprints": 0, "cooldown_seconds": 0.0, "max_entries": 0}
        return self._cooldown.stats()
