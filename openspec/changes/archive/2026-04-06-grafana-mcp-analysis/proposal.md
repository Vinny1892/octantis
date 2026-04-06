## Why

Octantis pre-fetches a fixed set of 5 PromQL queries via `prometheus-api-client` before the LLM sees any data. The LLM cannot request additional data — if the root cause involves disk pressure, network errors, or application-specific metrics, it has no way to investigate. This creates blind spots where the LLM identifies "something is wrong" but lacks evidence for root cause analysis. Additionally, the 3-layer pipeline (PreFilter → EventBatcher → Sampler) adds unnecessary overhead for a trigger-based model where events are signals, not data.

## What Changes

- **Add Grafana MCP client manager** — SSE connection to a shared `mcp-grafana` service exposing PromQL and LogQL tools to the LLM
- **Add optional K8s MCP support** — SSE connection to a K8s MCP server for Kubernetes resource queries, configured as optional but recommended
- **Replace `collector` node with `investigate` node** — LangGraph ToolNode with ReAct loop where the LLM autonomously queries Prometheus, Loki, and K8s via MCP tools
- **Add query budget and timeout** — Max 10 queries per investigation, 60s total timeout, 10s per MCP query
- **Add separate investigation LLM model config** — `LLM_INVESTIGATION_MODEL` env var, default Sonnet
- **Simplify pipeline** — Replace PreFilter with a lighter TriggerFilter, replace Sampler with FingerprintCooldown, **BREAKING** remove EventBatcher entirely
- **Add degraded mode** — When MCP is unavailable, analyze with event data only and notify operators of degradation
- **Add internal Prometheus metrics** — 9 metrics covering investigation, MCP queries, triggers, and LLM token usage
- **BREAKING** Remove `prometheus-api-client` dependency and `collectors/prometheus.py`
- **BREAKING** Remove `kubernetes` client dependency and `collectors/kubernetes.py`
- **BREAKING** Remove `EventBatcher` and `Sampler` classes
- **BREAKING** Replace `EnrichedEvent` with `InvestigationResult` in workflow state

## Capabilities

### New Capabilities
- `mcp-client`: MCP client manager for SSE connections to Grafana and K8s MCP servers, tool discovery, and health checking
- `investigation-workflow`: LangGraph ReAct subgraph where the LLM autonomously investigates using MCP tools with budget/timeout controls
- `trigger-filter`: Simplified event filter replacing PreFilter — detects anomalies, drops noise, no batching
- `fingerprint-cooldown`: Sliding-window cooldown suppressing repeated triggers for the same issue
- `investigation-metrics`: Internal Prometheus metrics for investigation, MCP, triggers, and LLM tokens

### Modified Capabilities
- `otlp-receiver-orchestrator`: Main loop changes from PreFilter → Batcher → Sampler → workflow to TriggerFilter → Cooldown → workflow

## Impact

- **Code removed**: `collectors/prometheus.py`, `collectors/kubernetes.py`, `pipeline/batcher.py`, `pipeline/sampler.py`, `graph/nodes/collector.py`
- **Code modified**: `config.py` (new MCP/investigation settings), `main.py` (new pipeline loop), `graph/workflow.py` (new investigate node), `graph/state.py` (InvestigationResult replaces EnrichedEvent), `graph/nodes/analyzer.py` (input changes), `graph/nodes/planner.py` (input changes), `graph/nodes/notifier.py` (degradation warning), `models/event.py` (new models, remove PrometheusContext)
- **Dependencies added**: `mcp[sse]`, `langchain-mcp-adapters`, `prometheus-client`
- **Dependencies removed**: `prometheus-api-client`, `kubernetes`
- **Config added**: `GRAFANA_MCP_URL`, `GRAFANA_MCP_API_KEY`, `K8S_MCP_URL` (optional), `LLM_INVESTIGATION_MODEL`, `INVESTIGATION_MAX_QUERIES`, `INVESTIGATION_TIMEOUT_SECONDS`, `INVESTIGATION_QUERY_TIMEOUT_SECONDS`
- **Tests**: All collector/batcher/sampler tests must be rewritten for new components
