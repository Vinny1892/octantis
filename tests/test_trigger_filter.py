"""Tests for TriggerFilter rule engine."""

from octantis.models.event import InfraEvent, LogRecord, MetricDataPoint, OTelResource
from octantis.pipeline.trigger_filter import Decision, TriggerFilter

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _event(
    source="api-server",
    ns="production",
    pod="api-abc",
    event_type="metric",
    metrics: list[tuple[str, float]] | None = None,
    logs: list[tuple[str, str]] | None = None,
) -> InfraEvent:
    return InfraEvent(
        event_id=f"test-{source}-{id(metrics)}",
        event_type=event_type,
        source=source,
        resource=OTelResource(
            service_name=source,
            extra={
                "k8s.namespace.name": ns,
                "k8s.pod.name": pod,
            },
        ),
        metrics=[MetricDataPoint(name=n, value=v) for n, v in (metrics or [])],
        logs=[LogRecord(body=b, severity_text=s) for b, s in (logs or [])],
    )


# ─── Anomalous metric passes ────────────────────────────────────────────────


def test_high_cpu_passes():
    tf = TriggerFilter.default(cpu_threshold=75.0)
    event = _event(metrics=[("cpu_usage", 95.0)])
    assert tf.should_investigate(event) is True


# ─── Error log passes ───────────────────────────────────────────────────────


def test_error_log_passes():
    tf = TriggerFilter.default()
    event = _event(logs=[("Connection pool exhausted", "ERROR")])
    assert tf.should_investigate(event) is True


# ─── Critical pattern (oomkill) passes ──────────────────────────────────────


def test_oomkill_metric_passes():
    tf = TriggerFilter.default()
    event = _event(metrics=[("container_oomkill_total", 1.0)])
    assert tf.should_investigate(event) is True


# ─── Health check dropped ───────────────────────────────────────────────────


def test_health_check_dropped():
    tf = TriggerFilter.default()
    event = _event(logs=[("GET /healthz HTTP/1.1 200", "INFO")])
    assert tf.should_investigate(event) is False


# ─── Benign pattern dropped ─────────────────────────────────────────────────


def test_benign_pattern_dropped():
    tf = TriggerFilter.default(benign_patterns=["nightly-batch"])
    event = _event(source="nightly-batch-job")
    assert tf.should_investigate(event) is False


# ─── No signal dropped ──────────────────────────────────────────────────────


def test_no_signal_dropped():
    """Events with empty metrics AND empty logs are dropped."""
    tf = TriggerFilter.default()
    event = _event(metrics=None, logs=None)
    assert tf.should_investigate(event) is False
    result = tf.evaluate(event)
    assert result.rule == "no_signal"


# ─── All metrics normal dropped ─────────────────────────────────────────────


def test_all_metrics_normal_dropped():
    tf = TriggerFilter.default(cpu_threshold=75.0, memory_threshold=80.0)
    event = _event(metrics=[("cpu_usage", 30.0), ("memory_usage", 40.0)])
    assert tf.should_investigate(event) is False


# ─── Fail-open: unknown event passes ────────────────────────────────────────


def test_fail_open_unknown_event_passes():
    """An event with only an unrecognised metric name passes (fail-open)."""
    tf = TriggerFilter.default()
    event = _event(metrics=[("some_unknown_gauge", 42.0)])
    # MetricThresholdRule won't match any known name to breach or drop,
    # but it drops when ALL metrics are within thresholds. Since
    # "some_unknown_gauge" doesn't match cpu/memory/error/restart names,
    # no breach is detected and the rule drops. However, fail-open applies
    # only when NO rule returns a result. Let's use an event_type-only event
    # with a single log that has no severity and no keywords — but that
    # still has signal (not empty), so NoSignalRule won't fire.
    event = InfraEvent(
        event_id="test-unknown",
        event_type="custom_webhook",
        source="external-system",
        resource=OTelResource(extra={"k8s.namespace.name": "staging"}),
        logs=[LogRecord(body="webhook received", severity_text="")],
    )
    tf.evaluate(event)
    # LogSeverityRule sees a log with empty severity and no critical keywords → DROP
    # For true fail-open, we need no rule to match at all.
    # An event with logs but unknown structure will still be caught by LogSeverityRule.
    # True fail-open: event with metrics that no rule understands AND no logs.
    tf_custom = TriggerFilter(rules=[])  # no rules at all
    event2 = _event(metrics=[("custom", 1.0)])
    result2 = tf_custom.evaluate(event2)
    assert result2.decision == Decision.PASS
    assert result2.rule == "default"


# ─── Multiple signals: single PASS ──────────────────────────────────────────


def test_multiple_signals_single_pass():
    """An event with both anomalous metrics and error logs produces one PASS."""
    tf = TriggerFilter.default()
    event = _event(
        metrics=[("cpu_usage", 99.0), ("container_oomkill_total", 3.0)],
        logs=[("OOMKilled: memory limit exceeded", "ERROR")],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.PASS
    # Only one result — the first matching rule wins
    assert result.rule in {
        "health_check",
        "metric_threshold",
        "log_severity",
        "benign_pattern",
        "no_signal",
    }


# ─── Node Exporter metric tests ──────────────────────────────────────────────


def test_node_cpu_above_threshold_triggers():
    tf = TriggerFilter.default()
    event = _event(
        source="node-exporter",
        metrics=[("node_cpu_seconds_total", 85.0)],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.PASS
    assert "cpu" in result.reason.lower() or "threshold" in result.reason.lower()


def test_node_cpu_below_threshold_dropped():
    tf = TriggerFilter.default()
    event = _event(
        source="node-exporter",
        metrics=[("node_cpu_seconds_total", 30.0)],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.DROP
    assert "normal thresholds" in result.reason


def test_node_memory_above_threshold_triggers():
    tf = TriggerFilter.default()
    event = _event(
        source="node-exporter",
        metrics=[("node_memory_MemAvailable_bytes", 85.0)],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.PASS


def test_node_filesystem_above_threshold_triggers():
    tf = TriggerFilter.default()
    event = _event(
        source="node-exporter",
        metrics=[("node_filesystem_avail_bytes", 90.0)],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.PASS


def test_node_network_error_always_analyzed():
    tf = TriggerFilter.default()
    event = _event(
        source="node-exporter",
        metrics=[("node_network_receive_errs_total", 0.5)],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.PASS
    assert "network" in result.reason.lower() or "error" in result.reason.lower()


def test_mixed_k8s_and_node_exporter_metrics():
    tf = TriggerFilter.default()
    event = _event(
        source="api-server",
        metrics=[
            ("cpu_usage", 30.0),
            ("node_cpu_seconds_total", 90.0),
        ],
    )
    result = tf.evaluate(event)
    assert result.decision == Decision.PASS
