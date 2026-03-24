"""Tests for pre-filter, batcher, and sampler."""

import asyncio
import time

import pytest

from octantis.models.event import InfraEvent, LogRecord, MetricDataPoint, OTelResource
from octantis.pipeline.batcher import EventBatcher, _batch_key, _merge_events
from octantis.pipeline.prefilter import (
    BenignPatternRule,
    Decision,
    HealthCheckRule,
    LogSeverityRule,
    MetricThresholdRule,
    PreFilter,
)
from octantis.pipeline.sampler import Sampler, _fingerprint


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _event(
    source="api-server",
    ns="production",
    pod="api-abc",
    event_type="metric",
    metrics: list[tuple[str, float]] | None = None,
    logs: list[tuple[str, str]] | None = None,  # (body, severity)
) -> InfraEvent:
    return InfraEvent(
        event_id=f"test-{source}-{id(metrics)}",
        event_type=event_type,
        source=source,
        resource=OTelResource(
            service_name=source,
            k8s_namespace=ns,
            k8s_pod_name=pod,
        ),
        metrics=[MetricDataPoint(name=n, value=v) for n, v in (metrics or [])],
        logs=[LogRecord(body=b, severity_text=s) for b, s in (logs or [])],
    )


# ─── Pre-filter: HealthCheckRule ─────────────────────────────────────────────

def test_health_check_rule_drops_probe_logs():
    rule = HealthCheckRule()
    event = _event(logs=[("GET /healthz HTTP/1.1 200", "INFO")])
    result = rule.evaluate(event)
    assert result is not None
    assert result.decision == Decision.DROP


def test_health_check_rule_passes_normal_logs():
    rule = HealthCheckRule()
    event = _event(logs=[("User login failed: invalid credentials", "ERROR")])
    assert rule.evaluate(event) is None


# ─── Pre-filter: MetricThresholdRule ─────────────────────────────────────────

def test_metric_threshold_drops_healthy_metrics():
    rule = MetricThresholdRule(cpu_ok_below=75.0, memory_ok_below=80.0)
    event = _event(metrics=[("cpu_usage", 50.0), ("memory_usage", 60.0)])
    result = rule.evaluate(rule._replace_event(event) if False else event)
    result = rule.evaluate(event)
    assert result is not None
    assert result.decision == Decision.DROP


def test_metric_threshold_passes_high_cpu():
    rule = MetricThresholdRule(cpu_ok_below=75.0)
    event = _event(metrics=[("cpu_usage", 90.0)])
    result = rule.evaluate(event)
    assert result is not None
    assert result.decision == Decision.PASS


def test_metric_threshold_passes_error_metric_by_name():
    """Metrics with 'error' in the name always pass regardless of value."""
    rule = MetricThresholdRule()
    event = _event(metrics=[("http_error_count", 0.0)])
    result = rule.evaluate(event)
    assert result is not None
    assert result.decision == Decision.PASS


def test_metric_threshold_passes_oom_metric():
    rule = MetricThresholdRule()
    event = _event(metrics=[("container_oomkill_total", 1.0)])
    result = rule.evaluate(event)
    assert result.decision == Decision.PASS


def test_metric_threshold_no_metrics_returns_none():
    rule = MetricThresholdRule()
    event = _event()
    assert rule.evaluate(event) is None


# ─── Pre-filter: LogSeverityRule ─────────────────────────────────────────────

def test_log_severity_drops_plain_info():
    rule = LogSeverityRule()
    event = _event(logs=[("Server started on port 8080", "INFO")])
    result = rule.evaluate(event)
    assert result.decision == Decision.DROP


def test_log_severity_passes_error_level():
    rule = LogSeverityRule()
    event = _event(logs=[("Connection pool exhausted", "ERROR")])
    result = rule.evaluate(event)
    assert result.decision == Decision.PASS


def test_log_severity_passes_info_with_critical_keyword():
    rule = LogSeverityRule()
    event = _event(logs=[("INFO: connection refused to database", "INFO")])
    result = rule.evaluate(event)
    assert result.decision == Decision.PASS


def test_log_severity_passes_panic_keyword():
    rule = LogSeverityRule()
    event = _event(logs=[("goroutine panic: nil pointer dereference", "DEBUG")])
    result = rule.evaluate(event)
    assert result.decision == Decision.PASS


# ─── Pre-filter: BenignPatternRule ───────────────────────────────────────────

def test_benign_pattern_drops_matching_source():
    rule = BenignPatternRule(patterns=["nightly-batch", "prometheus-scrape"])
    event = _event(source="nightly-batch-job")
    result = rule.evaluate(event)
    assert result.decision == Decision.DROP


def test_benign_pattern_passes_unmatched():
    rule = BenignPatternRule(patterns=["nightly-batch"])
    event = _event(source="api-server")
    assert rule.evaluate(event) is None


# ─── PreFilter integration ───────────────────────────────────────────────────

def test_prefilter_drops_health_probe():
    pf = PreFilter.default()
    event = _event(logs=[("GET /healthz 200", "INFO")])
    assert not pf.should_analyze(event)


def test_prefilter_passes_high_cpu():
    pf = PreFilter.default(cpu_threshold=75.0)
    event = _event(metrics=[("cpu_usage", 95.0)])
    assert pf.should_analyze(event)


def test_prefilter_passes_error_log():
    pf = PreFilter.default()
    event = _event(logs=[("OOMKilled: memory limit exceeded", "ERROR")])
    assert pf.should_analyze(event)


def test_prefilter_default_pass_no_rules_match():
    """Event with no metrics or logs passes by default (fail-open)."""
    pf = PreFilter.default()
    event = _event()
    assert pf.should_analyze(event)


# ─── Batcher ─────────────────────────────────────────────────────────────────

def test_batch_key_groups_by_workload():
    e1 = _event(ns="prod", pod="api-abc")
    e2 = _event(ns="prod", pod="api-abc")
    e3 = _event(ns="prod", pod="worker-xyz")
    assert _batch_key(e1) == _batch_key(e2)
    assert _batch_key(e1) != _batch_key(e3)


def test_merge_events_combines_metrics():
    e1 = _event(metrics=[("cpu", 80.0), ("memory", 60.0)])
    e2 = _event(metrics=[("cpu", 85.0), ("error_rate", 0.5)])
    merged = _merge_events([e1, e2])
    names = {m.name for m in merged.metrics}
    assert "cpu" in names
    assert "memory" in names
    assert "error_rate" in names


def test_merge_events_single_returns_original():
    e = _event(metrics=[("cpu", 50.0)])
    assert _merge_events([e]) is e


def test_merge_events_limits_logs():
    logs = [("log line", "INFO")] * 30
    e1 = _event(logs=logs[:15])
    e2 = _event(logs=logs[15:])
    merged = _merge_events([e1, e2])
    assert len(merged.logs) <= 20


@pytest.mark.asyncio
async def test_batcher_flushes_on_max_size():
    """Batcher flushes immediately when max_batch_size is reached."""
    batcher = EventBatcher(window_seconds=60.0, max_batch_size=3)
    events = [_event(source="svc", ns="prod", pod="pod-1") for _ in range(3)]
    batches = []

    async def _source():
        for e in events:
            yield e

    async for batch in batcher.run(_source()):
        batches.append(batch)

    assert len(batches) == 1
    assert batches[0].raw_payload["_batch_size"] == 3


@pytest.mark.asyncio
async def test_batcher_flushes_on_window():
    """Batcher flushes after window expires."""
    batcher = EventBatcher(window_seconds=0.1, max_batch_size=100)
    events = [_event(source="svc", ns="prod", pod="pod-1") for _ in range(2)]
    batches = []

    async def _source():
        for e in events:
            yield e
        await asyncio.sleep(0.3)  # let window expire

    async for batch in batcher.run(_source()):
        batches.append(batch)

    assert len(batches) >= 1


# ─── Sampler ─────────────────────────────────────────────────────────────────

def test_sampler_allows_first_occurrence():
    sampler = Sampler(cooldown_seconds=60.0)
    event = _event(metrics=[("cpu", 90.0)])
    assert sampler.should_analyze(event) is True


def test_sampler_suppresses_duplicate_within_cooldown():
    sampler = Sampler(cooldown_seconds=60.0)
    event = _event(metrics=[("cpu", 90.0)])
    assert sampler.should_analyze(event) is True
    assert sampler.should_analyze(event) is False


def test_sampler_allows_after_cooldown(monkeypatch):
    sampler = Sampler(cooldown_seconds=1.0)
    event = _event(metrics=[("cpu", 90.0)])
    assert sampler.should_analyze(event) is True

    # Manually expire the entry
    fp = _fingerprint(event)
    sampler._seen[fp].last_seen -= 2.0  # simulate 2s elapsed

    assert sampler.should_analyze(event) is True


def test_sampler_different_workloads_are_independent():
    sampler = Sampler(cooldown_seconds=60.0)
    e1 = _event(source="svc-a", ns="prod", pod="pod-a", metrics=[("cpu", 90.0)])
    e2 = _event(source="svc-b", ns="prod", pod="pod-b", metrics=[("cpu", 90.0)])
    assert sampler.should_analyze(e1) is True
    assert sampler.should_analyze(e2) is True


def test_sampler_evicts_on_max_entries():
    sampler = Sampler(cooldown_seconds=60.0, max_entries=2)
    e1 = _event(source="svc-a", pod="pod-a")
    e2 = _event(source="svc-b", pod="pod-b")
    e3 = _event(source="svc-c", pod="pod-c")
    sampler.should_analyze(e1)
    sampler.should_analyze(e2)
    sampler.should_analyze(e3)  # triggers eviction
    assert len(sampler._seen) <= 2
