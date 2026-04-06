## ADDED Requirements

### Requirement: Expose internal Prometheus metrics
The system SHALL expose internal Prometheus metrics on `:9090/metrics` via `prometheus-client`. This endpoint MUST be separate from the OTLP HTTP receiver on `:4318`.

#### Scenario: Metrics endpoint responds
- **WHEN** a GET request is made to `:9090/metrics`
- **THEN** the response contains Prometheus exposition format text with all registered metrics

### Requirement: Investigation duration metric
The system MUST record `octantis_investigation_duration_seconds` as a Prometheus histogram tracking the total time of each investigation (ReAct loop).

#### Scenario: Investigation duration recorded
- **WHEN** an investigation completes in 12.5 seconds
- **THEN** 12.5 is observed in the `octantis_investigation_duration_seconds` histogram

### Requirement: Investigation queries metric
The system MUST record `octantis_investigation_queries_total` as a Prometheus counter with a `datasource` label (promql, logql, k8s) tracking the number of MCP queries per investigation.

#### Scenario: Queries counted by datasource
- **WHEN** an investigation executes 3 PromQL queries and 2 LogQL queries
- **THEN** `octantis_investigation_queries_total{datasource="promql"}` increments by 3 and `{datasource="logql"}` increments by 2

### Requirement: MCP query duration metric
The system MUST record `octantis_mcp_query_duration_seconds` as a Prometheus histogram with a `datasource` label tracking individual MCP query latency.

#### Scenario: MCP query latency recorded
- **WHEN** a PromQL query takes 2.3 seconds
- **THEN** 2.3 is observed in `octantis_mcp_query_duration_seconds{datasource="promql"}`

### Requirement: MCP errors metric
The system MUST record `octantis_mcp_errors_total` as a Prometheus counter with an `error_type` label (timeout, connection, query) tracking MCP query failures.

#### Scenario: MCP timeout counted
- **WHEN** an MCP query times out
- **THEN** `octantis_mcp_errors_total{error_type="timeout"}` increments by 1

### Requirement: Trigger filter metric
The system MUST record `octantis_trigger_total` as a Prometheus counter with an `outcome` label (passed, dropped, cooldown) tracking trigger filter decisions.

#### Scenario: Trigger outcomes counted
- **WHEN** the trigger filter passes 5 events, drops 10, and cooldown suppresses 3
- **THEN** `octantis_trigger_total{outcome="passed"}` is 5, `{outcome="dropped"}` is 10, `{outcome="cooldown"}` is 3

### Requirement: LLM token metrics
The system MUST record three token counters with a `node` label (investigate, analyze, plan):
- `octantis_llm_tokens_input_total` — input tokens consumed
- `octantis_llm_tokens_output_total` — output tokens consumed
- `octantis_llm_tokens_total` — total tokens consumed (input + output)

#### Scenario: Token usage tracked per node
- **WHEN** the investigate node consumes 3000 input tokens and 800 output tokens
- **THEN** `octantis_llm_tokens_input_total{node="investigate"}` increments by 3000, `octantis_llm_tokens_output_total{node="investigate"}` increments by 800, and `octantis_llm_tokens_total{node="investigate"}` increments by 3800
