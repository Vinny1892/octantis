"""Tests for FingerprintCooldown."""

from octantis.models.event import InfraEvent, LogRecord, MetricDataPoint, OTelResource
from octantis.pipeline.cooldown import FingerprintCooldown, _fingerprint

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
                "k8s.deployment.name": "",
            },
        ),
        metrics=[MetricDataPoint(name=n, value=v) for n, v in (metrics or [])],
        logs=[LogRecord(body=b, severity_text=s) for b, s in (logs or [])],
    )


# ─── First occurrence passes ────────────────────────────────────────────────


def test_first_occurrence_passes():
    cd = FingerprintCooldown(cooldown_seconds=60.0)
    event = _event(metrics=[("cpu", 90.0)])
    assert cd.should_investigate(event) is True


# ─── Repeated within cooldown suppressed ────────────────────────────────────


def test_repeated_within_cooldown_suppressed():
    cd = FingerprintCooldown(cooldown_seconds=60.0)
    event = _event(metrics=[("cpu", 90.0)])
    assert cd.should_investigate(event) is True
    assert cd.should_investigate(event) is False
    assert cd.should_investigate(event) is False


# ─── Cooldown expired re-triggers ───────────────────────────────────────────


def test_cooldown_expired_retriggers():
    cd = FingerprintCooldown(cooldown_seconds=1.0)
    event = _event(metrics=[("cpu", 90.0)])
    assert cd.should_investigate(event) is True

    # Manually expire the entry by backdating last_seen
    fp = _fingerprint(event)
    cd._seen[fp].last_seen -= 2.0

    assert cd.should_investigate(event) is True


# ─── Sliding window resets timer ────────────────────────────────────────────


def test_sliding_window_resets_timer():
    """Each suppressed occurrence resets the cooldown timer."""
    cd = FingerprintCooldown(cooldown_seconds=10.0)
    event = _event(metrics=[("cpu", 90.0)])
    fp = _fingerprint(event)

    # First call — passes
    assert cd.should_investigate(event) is True
    initial_time = cd._seen[fp].last_seen

    # Second call — suppressed, but timer should advance
    assert cd.should_investigate(event) is False
    updated_time = cd._seen[fp].last_seen
    assert updated_time >= initial_time

    # Backdate to just before cooldown would expire from the RESET time
    # If sliding window works, the cooldown is measured from updated_time
    cd._seen[fp].last_seen = updated_time - 9.5  # 9.5s ago, cooldown is 10s
    assert cd.should_investigate(event) is False  # still within cooldown

    cd._seen[fp].last_seen = updated_time - 11.0  # 11s ago, cooldown is 10s
    assert cd.should_investigate(event) is True  # cooldown expired


# ─── LRU eviction when table full ───────────────────────────────────────────


def test_lru_eviction_when_table_full():
    cd = FingerprintCooldown(cooldown_seconds=60.0, max_entries=2)
    e1 = _event(source="svc-a", pod="pod-a")
    e2 = _event(source="svc-b", pod="pod-b")
    e3 = _event(source="svc-c", pod="pod-c")

    cd.should_investigate(e1)
    cd.should_investigate(e2)
    assert cd.stats()["tracked_fingerprints"] == 2

    cd.should_investigate(e3)  # triggers eviction of oldest
    assert cd.stats()["tracked_fingerprints"] == 2

    # The oldest entry (e1) should have been evicted, so it passes again
    fp1 = _fingerprint(e1)
    assert fp1 not in cd._seen


# ─── Different error messages produce different fingerprints ────────────────


def test_different_errors_produce_different_fingerprints():
    e1 = _event(
        logs=[("NullPointerException in UserService.getUser", "ERROR")],
    )
    e2 = _event(
        logs=[("ConnectionRefusedException: database unreachable", "ERROR")],
    )
    fp1 = _fingerprint(e1)
    fp2 = _fingerprint(e2)
    assert fp1 != fp2

    # Both should pass independently through cooldown
    cd = FingerprintCooldown(cooldown_seconds=60.0)
    assert cd.should_investigate(e1) is True
    assert cd.should_investigate(e2) is True
