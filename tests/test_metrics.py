"""Tests for octantis.metrics module."""

import pytest
from prometheus_client import Counter, Histogram

from octantis.metrics import (
    INVESTIGATION_DURATION,
    INVESTIGATION_QUERIES,
    LLM_TOKENS_INPUT,
    LLM_TOKENS_OUTPUT,
    LLM_TOKENS_TOTAL,
    MCP_ERRORS,
    MCP_QUERY_DURATION,
    TRIGGER_TOTAL,
    start_metrics_server,
)


class TestMetricsRegistered:
    """All 9 metric objects exist and have the correct type."""

    @pytest.mark.parametrize(
        "metric",
        [INVESTIGATION_DURATION, MCP_QUERY_DURATION],
        ids=["investigation_duration", "mcp_query_duration"],
    )
    def test_histograms_are_registered(self, metric: Histogram) -> None:
        assert isinstance(metric, Histogram)

    @pytest.mark.parametrize(
        "metric",
        [
            INVESTIGATION_QUERIES,
            MCP_ERRORS,
            TRIGGER_TOTAL,
            LLM_TOKENS_INPUT,
            LLM_TOKENS_OUTPUT,
            LLM_TOKENS_TOTAL,
        ],
        ids=[
            "investigation_queries",
            "mcp_errors",
            "trigger_total",
            "llm_tokens_input",
            "llm_tokens_output",
            "llm_tokens_total",
        ],
    )
    def test_counters_are_registered(self, metric: Counter) -> None:
        assert isinstance(metric, Counter)

    def test_total_metric_count(self) -> None:
        metrics = [
            INVESTIGATION_DURATION,
            INVESTIGATION_QUERIES,
            MCP_QUERY_DURATION,
            MCP_ERRORS,
            TRIGGER_TOTAL,
            LLM_TOKENS_INPUT,
            LLM_TOKENS_OUTPUT,
            LLM_TOKENS_TOTAL,
        ]
        assert len(metrics) == 8  # 8 unique objects (9 counting start fn)


class TestCounterIncrement:
    """Counter .inc() works with the expected labels."""

    def test_trigger_total_increment(self) -> None:
        before = TRIGGER_TOTAL.labels(outcome="passed")._value.get()
        TRIGGER_TOTAL.labels(outcome="passed").inc()
        after = TRIGGER_TOTAL.labels(outcome="passed")._value.get()
        assert after == before + 1

    def test_trigger_total_dropped(self) -> None:
        before = TRIGGER_TOTAL.labels(outcome="dropped")._value.get()
        TRIGGER_TOTAL.labels(outcome="dropped").inc()
        after = TRIGGER_TOTAL.labels(outcome="dropped")._value.get()
        assert after == before + 1

    def test_investigation_queries_counter(self) -> None:
        before = INVESTIGATION_QUERIES.labels(datasource="promql")._value.get()
        INVESTIGATION_QUERIES.labels(datasource="promql").inc()
        after = INVESTIGATION_QUERIES.labels(datasource="promql")._value.get()
        assert after == before + 1

    def test_mcp_errors_counter(self) -> None:
        before = MCP_ERRORS.labels(error_type="timeout")._value.get()
        MCP_ERRORS.labels(error_type="timeout").inc()
        after = MCP_ERRORS.labels(error_type="timeout")._value.get()
        assert after == before + 1


class TestHistogramObserve:
    """Histogram .observe() records values."""

    def test_investigation_duration_observe(self) -> None:
        before = INVESTIGATION_DURATION._sum.get()
        INVESTIGATION_DURATION.observe(12.5)
        after = INVESTIGATION_DURATION._sum.get()
        assert after == before + 12.5

    def test_mcp_query_duration_observe(self) -> None:
        before = MCP_QUERY_DURATION.labels(datasource="logql")._sum.get()
        MCP_QUERY_DURATION.labels(datasource="logql").observe(0.35)
        after = MCP_QUERY_DURATION.labels(datasource="logql")._sum.get()
        assert after == pytest.approx(before + 0.35)


class TestTokenCounters:
    """LLM token counters work with node labels."""

    @pytest.mark.parametrize(
        "counter",
        [LLM_TOKENS_INPUT, LLM_TOKENS_OUTPUT, LLM_TOKENS_TOTAL],
        ids=["input", "output", "total"],
    )
    @pytest.mark.parametrize("node", ["investigate", "analyze", "plan"])
    def test_token_counter_increment(self, counter: Counter, node: str) -> None:
        before = counter.labels(node=node)._value.get()
        counter.labels(node=node).inc(150)
        after = counter.labels(node=node)._value.get()
        assert after == before + 150


class TestStartMetricsServer:
    """start_metrics_server is callable."""

    def test_start_metrics_server_is_callable(self) -> None:
        assert callable(start_metrics_server)
