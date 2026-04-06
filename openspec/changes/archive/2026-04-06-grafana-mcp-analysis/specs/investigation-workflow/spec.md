## ADDED Requirements

### Requirement: Investigate node runs ReAct loop with MCP tools
The `investigate` node SHALL run a LangGraph ReAct-style subgraph where the LLM receives trigger event context and MCP tools, then iteratively queries observability data and reasons about results. The node MUST produce an `InvestigationResult` containing the original event, all query records, an evidence summary, and metadata.

#### Scenario: LLM investigates with PromQL and LogQL
- **WHEN** a trigger event enters the investigate node with Grafana MCP tools available
- **THEN** the LLM autonomously calls PromQL and/or LogQL queries via MCP tools, analyzes results, and produces an `InvestigationResult` with `queries_executed` and `evidence_summary`

#### Scenario: LLM investigates with K8s MCP
- **WHEN** a trigger event enters the investigate node with K8s MCP tools available
- **THEN** the LLM MAY call K8s queries via MCP tools alongside PromQL/LogQL queries

#### Scenario: LLM decides event is benign without querying
- **WHEN** the LLM receives a trigger event and determines it is benign from the trigger data alone
- **THEN** the system produces an `InvestigationResult` with zero queries and the LLM's reasoning in `evidence_summary`

### Requirement: Query budget enforcement
The investigate node MUST enforce a configurable maximum number of MCP queries per investigation (default 10, via `INVESTIGATION_MAX_QUERIES`). When the budget is exhausted, the ReAct loop MUST terminate and the LLM MUST produce a final analysis with data collected so far.

#### Scenario: Budget exhausted
- **WHEN** the LLM has executed 10 MCP queries in a single investigation
- **THEN** the ReAct loop terminates, `budget_exhausted` is set to `true` on `InvestigationResult`, and the LLM produces an analysis with available data

### Requirement: Investigation timeout
The investigate node MUST enforce a configurable total timeout per investigation (default 60s, via `INVESTIGATION_TIMEOUT_SECONDS`). When the timeout fires, the ReAct loop MUST terminate and produce a partial result.

#### Scenario: Timeout reached
- **WHEN** 60 seconds have elapsed since the investigation started
- **THEN** the ReAct loop terminates, the system logs `investigation.timeout` with `queries_completed` and `elapsed_s`, and produces an `InvestigationResult` with partial data

### Requirement: Separate investigation LLM model
The investigate node MUST use the model configured in `LLM_INVESTIGATION_MODEL` (default: same as `LLM_MODEL`, which defaults to `claude-sonnet-4-6`). This MUST be independent from the model used by the analyze and plan nodes.

#### Scenario: Different model for investigation
- **WHEN** `LLM_INVESTIGATION_MODEL` is set to `claude-opus-4-6` and `LLM_MODEL` is `claude-sonnet-4-6`
- **THEN** the investigate node uses Opus for tool calling, while analyze and plan nodes use Sonnet

### Requirement: Degraded investigation when MCP unavailable
When no MCP tools are available (all servers degraded), the investigate node MUST produce an `InvestigationResult` with `mcp_degraded: true`, zero queries, and an `evidence_summary` based only on the trigger event data.

#### Scenario: All MCP servers unavailable
- **WHEN** a trigger event enters the investigate node and no MCP tools are available
- **THEN** the LLM analyzes the trigger event data only, `mcp_degraded` is set to `true`, and `investigation.degraded` is logged

### Requirement: All queries return empty data
When the LLM queries MCP and all results are empty or contain no data, the investigate node MUST produce an `InvestigationResult` with the attempted queries logged and an `evidence_summary` indicating insufficient data.

#### Scenario: Empty query results
- **WHEN** the LLM executes 3 PromQL queries and all return empty results
- **THEN** the `InvestigationResult` contains all 3 queries in `queries_executed`, and `evidence_summary` indicates insufficient data was found

### Requirement: Investigation records token usage
The investigate node MUST track input and output tokens consumed during the ReAct loop and record them in `InvestigationResult.tokens_input` and `InvestigationResult.tokens_output`.

#### Scenario: Token tracking
- **WHEN** an investigation completes
- **THEN** `tokens_input` and `tokens_output` reflect the total tokens consumed across all LLM calls in the ReAct loop

### Requirement: Updated workflow graph
The LangGraph workflow MUST be restructured: `START → investigate → analyze → (conditional) → plan → notify → END`. The `collect` node MUST be removed. The `analyze` node MUST read `investigation` (InvestigationResult) from state instead of `enriched_event`.

#### Scenario: Workflow executes new graph
- **WHEN** a trigger event is processed by the workflow
- **THEN** it flows through investigate → analyze → (conditional plan → notify) without a collect node
