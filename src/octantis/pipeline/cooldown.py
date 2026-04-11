"""Fingerprint cooldown: deduplication to avoid re-investigating the same issue.

Once an event fingerprint has been investigated, subsequent identical events
within the cooldown window are suppressed. This prevents alert fatigue and
unnecessary LLM cost when the same issue fires repeatedly.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import structlog

from octantis.models.event import InfraEvent

log = structlog.get_logger(__name__)


def _fingerprint(event: InfraEvent) -> str:
    """Stable fingerprint based on workload identity + metric/log shape.

    Deliberately coarse — two events from the same pod reporting the same
    metric names should produce the same fingerprint even if values differ.
    """
    resource = event.resource
    k8s_ns = resource.extra.get("k8s.namespace.name", "")
    k8s_deploy = resource.extra.get("k8s.deployment.name", "")
    k8s_pod = resource.extra.get("k8s.pod.name", "")

    parts = [
        k8s_ns,
        k8s_deploy or k8s_pod or event.source,
        event.event_type,
        ",".join(sorted(m.name for m in event.metrics)),
    ]
    # Include first log body prefix for log events so different error
    # types get distinct fingerprints
    if event.logs:
        # Truncate to avoid minor message variations creating unique fingerprints
        parts.append(event.logs[-1].body[:60])

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class _Entry:
    last_seen: float
    count: int = 1


class FingerprintCooldown:
    """Tracks recently investigated event fingerprints and suppresses duplicates.

    Each occurrence within the cooldown window resets the timer (sliding window).
    When the table exceeds max_entries, the oldest entry is evicted (LRU).

    Args:
        cooldown_seconds: How long to suppress repeated identical events.
        max_entries: Maximum fingerprints to track (LRU eviction).
    """

    def __init__(
        self,
        cooldown_seconds: float = 300.0,
        max_entries: int = 1000,
    ) -> None:
        self._cooldown = cooldown_seconds
        self._max = max_entries
        self._seen: dict[str, _Entry] = {}

    def should_investigate(self, event: InfraEvent) -> bool:
        """Return True if this event should be investigated."""
        fp = _fingerprint(event)
        now = time.monotonic()
        entry = self._seen.get(fp)

        if entry is None:
            self._record(fp, now)
            log.debug(
                "cooldown.first_seen",
                event_id=event.event_id,
                fingerprint=fp,
            )
            return True

        elapsed = now - entry.last_seen
        if elapsed >= self._cooldown:
            log.debug(
                "cooldown.expired",
                event_id=event.event_id,
                fingerprint=fp,
                elapsed_s=round(elapsed),
                suppressed_count=entry.count - 1,
            )
            self._record(fp, now)
            return True

        # Within cooldown — suppress, but reset the sliding window timer
        entry.count += 1
        entry.last_seen = now
        log.info(
            "cooldown.suppressed",
            event_id=event.event_id,
            fingerprint=fp,
            cooldown_remaining_s=round(self._cooldown - elapsed),
            suppressed_count=entry.count - 1,
        )
        return False

    def _record(self, fp: str, now: float) -> None:
        if len(self._seen) >= self._max:
            # Evict the oldest entry (LRU)
            oldest = min(self._seen, key=lambda k: self._seen[k].last_seen)
            log.debug(
                "cooldown.eviction",
                evicted_fingerprint=oldest,
                table_size=len(self._seen),
            )
            del self._seen[oldest]
        self._seen[fp] = _Entry(last_seen=now)

    def stats(self) -> dict:
        """Return current state metrics."""
        return {
            "tracked_fingerprints": len(self._seen),
            "cooldown_seconds": self._cooldown,
            "max_entries": self._max,
        }
