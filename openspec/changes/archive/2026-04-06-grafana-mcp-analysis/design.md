## Context

Octantis is an intelligent infrastructure monitoring agent for EKS/Kubernetes. It receives OTLP telemetry events, runs them through a filtering pipeline, enriches them with static Prometheus + K8s queries, and sends enriched data to an LLM for severity classification and remediation planning.

Current architecture:
- `collectors/prometheus.py` — 5 hardcoded PromQL queries via `prometheus-api-client`
- `collectors/kubernetes.py` — Direct K8s API calls via `kubernetes` Python client
- `pipeline/prefilter.py` — 5-rule chain (health check, metric threshold, log severity, benign pattern, event type allowlist)
- `pipeline/batcher.py` — Groups events by workload in 30s windows, merges into single InfraEvent
- `pipeline/sampler.py` — Fingerprint-based cooldown (5min) to suppress duplicate LLM calls
- `graph/nodes/collector.py` — Orchestrates PrometheusCollector + KubernetesCollector
- `graph/nodes/analyzer.py` — LLM severity classification via `litellm.acompletion` (no tool calling)
- LangGraph workflow: `collect → analyze → plan → notify`

The system uses `litellm` for LLM calls, `langgraph` for workflow orchestration, `structlog` for logging, and `pydantic` for data models.

## Goals / Non-Goals

**Goals:**
- LLM autonomously queries Prometheus (PromQL) and Loki (LogQL) via Grafana MCP during investigation
- K8s context available via optional K8s MCP server
- Pipeline simplified from 5 components to 3 (TriggerFilter + Cooldown + workflow)
- Investigation bounded by query budget (10) and timeout (60s)
- Operators can configure a separate, more capable LLM model for investigation
- System continues operating (degraded) when MCP servers are unavailable, with operator notification
- Internal Prometheus metrics for investigation, MCP, triggers, and token usage

**Non-Goals:**
- Tempo / trace analysis
- Alertmanager integration
- Multi-tenant / multi-cluster support
- Grafana dashboard auto-generation
- Provisioning Grafana, Prometheus, or Loki instances

## Decisions

### 1. MCP via SSE to shared service

Connect to `mcp-grafana` and optionally `mcp-k8s` via SSE transport. Both MCP servers run as separate Deployments in the cluster, not as sidecars.

**Rationale**: The Grafana MCP server will be reused by ELK integration and other consumers. A shared service allows independent scaling and a single point of configuration.

**Alternative rejected**: stdio subprocess — not shareable, one process per Octantis replica.
**Alternative rejected**: Direct Grafana HTTP API — no tool abstraction, LLM can't use as tools natively.

### 2. LangGraph ToolNode with ReAct loop

Use `langchain-mcp-adapters` to convert MCP tools to LangChain tools. Build a ReAct-style subgraph within the `investigate` node where the LLM iteratively calls tools and reasons about results.

The query budget is tracked as a counter in the graph state. When budget is exhausted or timeout fires, the loop terminates and forces the LLM to produce a final `InvestigationResult`.

**Rationale**: Idiomatic for the existing LangGraph architecture. ToolNode handles tool routing automatically.

**Alternative rejected**: Manual litellm tool_use loop — duplicates LangGraph's loop logic.

### 3. K8s MCP as optional recommended datasource

Remove `kubernetes` Python client. K8s context is available via a separate K8s MCP server. When `K8S_MCP_URL` is configured, its tools are added to the LLM's toolset alongside Grafana MCP tools.

**Rationale**: Uniform tool interface for the LLM. Avoids maintaining two different data access patterns.

**Alternative rejected**: Keep kubernetes client as separate tools — inconsistent with MCP approach.

### 4. Separate LLM model for investigation

Add `LLM_INVESTIGATION_MODEL` config. Default: same as `LLM_MODEL` (claude-sonnet-4-6). Operators can override with a more capable model (e.g., Opus) for the investigation node without affecting analyzer/planner.

**Rationale**: Investigation is the most complex LLM task (multi-step tool calling). The decision on which model to use belongs to the operator, not the developer.

### 5. MCP Client Manager as singleton

Create an `MCPClientManager` class that:
1. Holds SSE client sessions for each configured MCP server
2. Connects at startup, discovers available tools
3. Exposes `get_tools() -> list[BaseTool]` for LangGraph integration
4. Tracks connection health, reconnects on failure
5. Reports degraded status per-server

The manager is instantiated once in `main.py` and passed to the workflow builder.

### 6. Simplify pipeline to TriggerFilter + FingerprintCooldown

- **TriggerFilter**: Refactor from `PreFilter`. Keep HealthCheckRule, MetricThresholdRule, LogSeverityRule, BenignPatternRule. Remove EventTypeAllowlistRule (unnecessary with trigger model). Rename class for clarity.
- **FingerprintCooldown**: Extract fingerprint + cooldown logic from `Sampler`. Same algorithm (namespace + workload + event type + metric names hash, sliding window, LRU eviction). Rename for clarity.
- **Remove**: `EventBatcher` entirely — no more batching, events flow directly.

### 7. New data models

- `MCPQueryRecord` — Records each MCP query (tool name, query string, result summary, duration, datasource, error)
- `InvestigationResult` — Replaces `EnrichedEvent`. Contains original event, query records, evidence summary, degradation status, budget status, duration, token counts
- Remove `PrometheusContext` from `models/event.py` (replaced by MCP query results)
- Keep `KubernetesContext` for now but mark as deprecated (K8s data now comes via MCP)

### 8. Updated workflow graph

```
START → investigate → analyze → (conditional) → plan → notify → END
                                     └──────────────────────────→ END
```

The `collect` node is removed. The `investigate` node is the new entry point. It runs the ReAct loop and produces `InvestigationResult`. The `analyze` node reads `investigation` instead of `enriched_event`.

### 9. Degraded mode with operator notification

When MCP connection fails:
1. Log warning with server URL
2. Set `mcp_degraded: true` on `InvestigationResult`
3. LLM analyzes with trigger event data only (no tools)
4. Notify node appends degradation warning to Slack/Discord messages

### 10. Internal Prometheus metrics

Use `prometheus-client` library. Expose metrics on `:9090/metrics` via a lightweight HTTP handler (separate from the OTLP HTTP receiver on :4318).

9 metrics total:
- `octantis_investigation_duration_seconds` (histogram)
- `octantis_investigation_queries_total` (counter, label: datasource)
- `octantis_mcp_query_duration_seconds` (histogram, label: datasource)
- `octantis_mcp_errors_total` (counter, label: error_type)
- `octantis_trigger_total` (counter, label: outcome)
- `octantis_llm_tokens_input_total` (counter, label: node)
- `octantis_llm_tokens_output_total` (counter, label: node)
- `octantis_llm_tokens_total` (counter, label: node)

## Risks / Trade-offs

- **LLM writes poor PromQL/LogQL queries** → Include example queries and common patterns in the investigation system prompt. The ReAct loop allows the LLM to retry with corrected queries.
- **MCP SSE connection instability** → Reconnect logic in MCPClientManager. Degraded mode ensures the pipeline doesn't stop.
- **Investigation latency variability** → Hard timeout at 60s prevents runaway investigations. Budget cap at 10 queries bounds the work.
- **langchain-mcp-adapters compatibility** → New dependency. Pin version in pyproject.toml. If incompatible with current langgraph version, fall back to manual tool wrapping.
- **Losing K8s context when K8s MCP is not configured** → Document K8s MCP as recommended. Investigation quality degrades without it but Prometheus + Loki cover most diagnostic needs.
- **In-memory cooldown lost on restart** → Acceptable for v1. A few duplicate investigations on restart are harmless. Consider Redis-backed cooldown if Octantis scales to multiple replicas.
