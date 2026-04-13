# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trigger filter: rule-based gate that decides if an event warrants investigation.

Evaluates cheap, deterministic rules to decide if an event contains enough
signal to trigger an LLM investigation. Rules are evaluated in order; the
first match wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

import structlog

from octantis.models.event import InfraEvent

log = structlog.get_logger(__name__)


class Decision(str, Enum):
    PASS = "pass"  # trigger investigation
    DROP = "drop"  # discard silently


@dataclass
class FilterResult:
    decision: Decision
    rule: str
    reason: str


class Rule(Protocol):
    name: str

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        """Return a FilterResult if this rule matches, None to defer to next rule."""
        ...


# ─── Concrete rules ──────────────────────────────────────────────────────────


@dataclass
class HealthCheckRule:
    """Drop liveness/readiness probe and healthz log events."""

    name: str = "health_check"

    _PROBE_PATTERNS: list[re.Pattern] = field(
        default_factory=lambda: [
            re.compile(r"GET /health", re.IGNORECASE),
            re.compile(r"GET /healthz", re.IGNORECASE),
            re.compile(r"GET /readyz", re.IGNORECASE),
            re.compile(r"GET /livez", re.IGNORECASE),
            re.compile(r"GET /ping", re.IGNORECASE),
            re.compile(r"kube-probe/", re.IGNORECASE),
        ]
    )

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        for log_record in event.logs:
            for pattern in self._PROBE_PATTERNS:
                if pattern.search(log_record.body):
                    return FilterResult(
                        decision=Decision.DROP,
                        rule=self.name,
                        reason=f"health probe log: {log_record.body[:80]}",
                    )
        return None


@dataclass
class MetricThresholdRule:
    """Drop metric events where all values are within normal operating ranges.

    Thresholds are tunable via config. All conditions must be satisfied
    simultaneously for the event to be dropped — if any metric exceeds
    its threshold, the event passes through.
    """

    name: str = "metric_threshold"

    # Thresholds for "boring" values — drop if ALL metrics are below these
    cpu_ok_below: float = 75.0  # %
    memory_ok_below: float = 80.0  # %
    error_rate_ok_below: float = 0.01  # req/s
    restart_count_ok_below: int = 3  # cumulative restarts

    # Metric name substrings that indicate problems regardless of value
    _ALWAYS_ANALYZE_NAMES: frozenset[str] = frozenset(
        {
            "oomkill",
            "eviction",
            "failed",
            "error",
            "crash",
            "panic",
            "timeout",
        }
    )

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        if not event.metrics:
            return None  # no metrics → let other rules decide

        # If any metric name hints at a problem, always analyze
        for m in event.metrics:
            name_lower = m.name.lower()
            for keyword in self._ALWAYS_ANALYZE_NAMES:
                if keyword in name_lower:
                    return FilterResult(
                        decision=Decision.PASS,
                        rule=self.name,
                        reason=f"metric name contains '{keyword}': {m.name}",
                    )

        # Map metric names to thresholds
        breached: list[str] = []
        for m in event.metrics:
            name = m.name.lower()
            if (
                ("cpu" in name and m.value >= self.cpu_ok_below)
                or ("memory" in name and m.value >= self.memory_ok_below)
                or ("filesystem" in name and m.value >= self.memory_ok_below)
                or ("network" in name and m.value >= self.error_rate_ok_below)
            ):
                breached.append(f"{m.name}={m.value:.1f}%")
            elif "error" in name and m.value >= self.error_rate_ok_below:
                breached.append(f"{m.name}={m.value:.3f}")
            elif "restart" in name and m.value >= self.restart_count_ok_below:
                breached.append(f"{m.name}={int(m.value)}")

        if breached:
            return FilterResult(
                decision=Decision.PASS,
                rule=self.name,
                reason=f"threshold breached: {', '.join(breached)}",
            )

        # All metrics look healthy → drop
        return FilterResult(
            decision=Decision.DROP,
            rule=self.name,
            reason="all metrics within normal thresholds",
        )


@dataclass
class LogSeverityRule:
    """Drop INFO/DEBUG logs that contain no critical keywords."""

    name: str = "log_severity"

    _CRITICAL_KEYWORDS: list[re.Pattern] = field(
        default_factory=lambda: [
            re.compile(r"\b(error|exception|panic|fatal|critical|crash)\b", re.IGNORECASE),
            re.compile(r"\b(oom|killed|evicted|backoff|throttl)\b", re.IGNORECASE),
            re.compile(
                r"\b(timeout|connection refused|refused|unreachable)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\b(failed|failure|cannot|unable to)\b", re.IGNORECASE),
        ]
    )

    _BORING_SEVERITIES: frozenset[str] = frozenset(
        {
            "INFO",
            "DEBUG",
            "TRACE",
            "info",
            "debug",
            "trace",
        }
    )

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        if not event.logs:
            return None

        for record in event.logs:
            # If severity is already elevated → always analyze
            sev = (record.severity_text or "").upper()
            if sev in {"ERROR", "FATAL", "CRITICAL", "WARN", "WARNING"}:
                return FilterResult(
                    decision=Decision.PASS,
                    rule=self.name,
                    reason=f"log severity={sev}",
                )
            # INFO/DEBUG with critical keywords → analyze
            if sev in self._BORING_SEVERITIES or not sev:
                for pattern in self._CRITICAL_KEYWORDS:
                    if pattern.search(record.body):
                        return FilterResult(
                            decision=Decision.PASS,
                            rule=self.name,
                            reason=f"critical keyword in log: {record.body[:100]}",
                        )

        # All logs are boring INFO/DEBUG with no keywords → drop
        return FilterResult(
            decision=Decision.DROP,
            rule=self.name,
            reason="only low-severity logs with no critical keywords",
        )


@dataclass
class BenignPatternRule:
    """Drop events matching known-benign patterns (configurable regexes)."""

    name: str = "benign_pattern"
    patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        if not self._compiled:
            return None

        # Check source name, event type, and log bodies
        candidates = [event.source, event.event_type]
        for record in event.logs:
            candidates.append(record.body)

        for text in candidates:
            for pattern in self._compiled:
                if pattern.search(text):
                    return FilterResult(
                        decision=Decision.DROP,
                        rule=self.name,
                        reason=(f"matched benign pattern '{pattern.pattern}' in '{text[:80]}'"),
                    )
        return None


@dataclass
class NoSignalRule:
    """Drop events with no metrics AND no logs — nothing to trigger on."""

    name: str = "no_signal"

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        if not event.metrics and not event.logs:
            return FilterResult(
                decision=Decision.DROP,
                rule=self.name,
                reason="event has no metrics and no logs",
            )
        return None


# ─── Trigger filter engine ───────────────────────────────────────────────────


class TriggerFilter:
    """Evaluates a chain of rules and returns a final FilterResult.

    Rules are evaluated in order. The first rule that returns a result
    (PASS or DROP) terminates the chain. If no rule matches, the event
    passes by default (fail-open).
    """

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    @classmethod
    def default(
        cls,
        cpu_threshold: float = 75.0,
        memory_threshold: float = 80.0,
        error_rate_threshold: float = 0.01,
        benign_patterns: list[str] | None = None,
    ) -> TriggerFilter:
        """Build a trigger filter with the standard rule chain."""
        rules: list[Rule] = [
            NoSignalRule(),
            HealthCheckRule(),
            BenignPatternRule(patterns=benign_patterns or []),
            MetricThresholdRule(
                cpu_ok_below=cpu_threshold,
                memory_ok_below=memory_threshold,
                error_rate_ok_below=error_rate_threshold,
            ),
            LogSeverityRule(),
        ]
        return cls(rules)

    def evaluate(self, event: InfraEvent) -> FilterResult:
        for rule in self._rules:
            result = rule.evaluate(event)
            if result is not None:
                log.debug(
                    "trigger_filter.rule_matched",
                    event_id=event.event_id,
                    rule=result.rule,
                    decision=result.decision,
                    reason=result.reason,
                )
                return result

        # Default: fail-open — pass unknown events to investigation
        return FilterResult(
            decision=Decision.PASS,
            rule="default",
            reason="no rule matched, passing to investigation",
        )

    def should_investigate(self, event: InfraEvent) -> bool:
        return self.evaluate(event).decision == Decision.PASS
