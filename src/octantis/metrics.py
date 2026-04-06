"""Internal Prometheus metrics for Octantis."""

from prometheus_client import Counter, Histogram, start_http_server

# Investigation
INVESTIGATION_DURATION = Histogram(
    "octantis_investigation_duration_seconds",
    "Total investigation time (ReAct loop)",
)

INVESTIGATION_QUERIES = Counter(
    "octantis_investigation_queries_total",
    "Number of MCP queries per investigation",
    ["datasource"],  # promql, logql, k8s
)

# MCP
MCP_QUERY_DURATION = Histogram(
    "octantis_mcp_query_duration_seconds",
    "Latency per individual MCP query",
    ["datasource"],  # promql, logql, k8s
)

MCP_ERRORS = Counter(
    "octantis_mcp_errors_total",
    "MCP query failures",
    ["error_type"],  # timeout, connection, query
)

# Trigger
TRIGGER_TOTAL = Counter(
    "octantis_trigger_total",
    "Trigger filter decisions",
    ["outcome"],  # passed, dropped, cooldown
)

# LLM Tokens
LLM_TOKENS_INPUT = Counter(
    "octantis_llm_tokens_input_total",
    "LLM input tokens consumed",
    ["node"],  # investigate, analyze, plan
)

LLM_TOKENS_OUTPUT = Counter(
    "octantis_llm_tokens_output_total",
    "LLM output tokens consumed",
    ["node"],  # investigate, analyze, plan
)

LLM_TOKENS_TOTAL = Counter(
    "octantis_llm_tokens_total",
    "Total LLM tokens consumed (input + output)",
    ["node"],  # investigate, analyze, plan
)


def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)
