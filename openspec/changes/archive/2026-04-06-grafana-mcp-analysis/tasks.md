## 1. Dependencies & Config

- [x] 1.1 Update pyproject.toml: add `mcp[sse]`, `langchain-mcp-adapters`, `prometheus-client`; remove `prometheus-api-client`, `kubernetes`
- [x] 1.2 Add MCP settings to `config.py`: `GrafanaMCPSettings` (url, api_key), `K8sMCPSettings` (url, optional), `InvestigationSettings` (model, max_queries, timeout_seconds, query_timeout_seconds)
- [x] 1.3 Add `MetricsSettings` to `config.py` for Prometheus metrics port (default 9090)
- [x] 1.4 Update `Settings` class: add `grafana_mcp`, `k8s_mcp`, `investigation`, `metrics` fields; remove `prometheus` field
- [x] 1.5 Update `.env.example` with new MCP and investigation env vars

## 2. Data Models

- [x] 2.1 Add `MCPQueryRecord` model to `models/event.py` (tool_name, query, result_summary, duration_ms, datasource, error)
- [x] 2.2 Add `InvestigationResult` model to `models/event.py` (original_event, queries_executed, evidence_summary, mcp_servers_used, mcp_degraded, budget_exhausted, investigation_duration_s, tokens_input, tokens_output)
- [x] 2.3 Remove `PrometheusContext` from `models/event.py`
- [x] 2.4 Remove `EnrichedEvent` from `models/event.py` (or mark deprecated)
- [x] 2.5 Update `models/__init__.py` exports: add InvestigationResult, MCPQueryRecord; remove EnrichedEvent, PrometheusContext
- [x] 2.6 Update `graph/state.py`: replace `enriched_event: EnrichedEvent` with `investigation: InvestigationResult`

## 3. MCP Client Manager

- [x] 3.1 Create `mcp_client/__init__.py` with `MCPClientManager` export
- [x] 3.2 Implement `MCPClientManager` class: SSE connection to Grafana MCP, tool discovery, `get_tools()` returning LangChain tools via `langchain-mcp-adapters`
- [x] 3.3 Add optional K8s MCP SSE connection: connects when `K8S_MCP_URL` is configured, merges tools into `get_tools()`
- [x] 3.4 Implement degraded mode: `get_degraded_servers()`, connection failure handling, reconnect logic
- [x] 3.5 Add MCP authentication: pass `GRAFANA_MCP_API_KEY` as header, validate key presence at startup
- [x] 3.6 Add per-query timeout: cancel MCP queries exceeding `INVESTIGATION_QUERY_TIMEOUT_SECONDS`
- [x] 3.7 Write unit tests for MCPClientManager (connection, tool discovery, degraded mode, timeout)

## 4. Investigation Workflow

- [x] 4.1 Create `graph/nodes/investigator.py` with `investigate_node` function
- [x] 4.2 Implement ReAct subgraph: LLM receives trigger event context + MCP tools, iterates via LangGraph ToolNode
- [x] 4.3 Implement query budget counter in graph state: terminate loop at max_queries, set budget_exhausted
- [x] 4.4 Implement investigation timeout: asyncio timeout wrapping the ReAct loop, produce partial result
- [x] 4.5 Implement separate LLM model: use `LLM_INVESTIGATION_MODEL` for the investigate node
- [x] 4.6 Implement degraded investigation: when no MCP tools available, LLM analyzes trigger event data only, set mcp_degraded
- [x] 4.7 Implement token tracking: capture input/output tokens from LLM responses, record in InvestigationResult
- [x] 4.8 Write investigation system prompt with PromQL/LogQL example queries and common patterns
- [x] 4.9 Write unit tests for investigate_node (normal flow, budget exhaustion, timeout, degraded mode, no queries)

## 5. Trigger Filter

- [x] 5.1 Create `pipeline/trigger_filter.py` by refactoring from `PreFilter`: keep HealthCheckRule, MetricThresholdRule, LogSeverityRule, BenignPatternRule; remove EventTypeAllowlistRule
- [x] 5.2 Add no-signal rule: drop events with empty metrics and empty logs
- [x] 5.3 Rename class to `TriggerFilter` with `should_investigate(event) -> bool` method
- [x] 5.4 Write unit tests for TriggerFilter (anomaly detection, health check drop, benign drop, no-signal drop, fail-open)

## 6. Fingerprint Cooldown

- [x] 6.1 Create `pipeline/cooldown.py` by extracting logic from `Sampler`: fingerprint hash, sliding window, LRU eviction
- [x] 6.2 Rename class to `FingerprintCooldown` with `should_investigate(event) -> bool` method
- [x] 6.3 Ensure fingerprint includes log body prefix (first 60 chars of last log)
- [x] 6.4 Write unit tests for FingerprintCooldown (first occurrence, suppression, expiry, sliding window, LRU eviction, different errors)

## 7. Internal Metrics

- [x] 7.1 Create `metrics.py` module with all 9 Prometheus metrics (investigation_duration, investigation_queries, mcp_query_duration, mcp_errors, trigger_total, tokens_input, tokens_output, tokens_total)
- [x] 7.2 Add metrics HTTP server on `:9090/metrics` using `prometheus-client` start_http_server
- [x] 7.3 Instrument investigate_node: record investigation_duration, investigation_queries, tokens
- [x] 7.4 Instrument MCPClientManager: record mcp_query_duration, mcp_errors
- [x] 7.5 Instrument TriggerFilter and FingerprintCooldown: record trigger_total
- [x] 7.6 Write unit tests for metrics registration and instrumentation

## 8. Workflow Rewiring

- [x] 8.1 Update `graph/workflow.py`: replace `collect` node with `investigate` node, update edges (START → investigate → analyze)
- [x] 8.2 Update `graph/nodes/analyzer.py`: read `investigation` (InvestigationResult) from state instead of `enriched_event`, build user message from evidence_summary and query records
- [x] 8.3 Update `graph/nodes/planner.py`: read `investigation` from state instead of `enriched_event`
- [x] 8.4 Update `graph/nodes/notifier.py`: add MCP degradation warning to Slack/Discord messages when `investigation.mcp_degraded` is true
- [x] 8.5 Update `graph/nodes/__init__.py`: export `investigate_node` instead of `collector_node`

## 9. Main Loop & Cleanup

- [x] 9.1 Update `main.py`: instantiate MCPClientManager, TriggerFilter, FingerprintCooldown; remove Batcher/Sampler; wire new pipeline loop (filter → cooldown → workflow)
- [x] 9.2 Add MCPClientManager startup/shutdown in main loop (connect at start, close at stop)
- [x] 9.3 Start metrics HTTP server in main loop
- [x] 9.4 Delete `collectors/prometheus.py`
- [x] 9.5 Delete `collectors/kubernetes.py`
- [x] 9.6 Delete `collectors/__init__.py` (or empty it)
- [x] 9.7 Delete `pipeline/batcher.py`
- [x] 9.8 Delete `pipeline/sampler.py`
- [x] 9.9 Delete `graph/nodes/collector.py`
- [x] 9.10 Update `pipeline/__init__.py`: export TriggerFilter, FingerprintCooldown; remove PreFilter, EventBatcher, Sampler

## 10. Test Updates

- [x] 10.1 Delete old tests: test_batcher, test_sampler, test_collector (if they exist)
- [x] 10.2 Update existing analyzer tests to use InvestigationResult instead of EnrichedEvent
- [x] 10.3 Update existing planner tests to use InvestigationResult
- [x] 10.4 Update existing notifier tests to verify MCP degradation warning
- [x] 10.5 Write integration test: trigger event → filter → cooldown → investigate (mocked MCP) → analyze → plan → notify
- [x] 10.6 Run full test suite and fix any remaining failures

## 11. Deployment Examples

- [x] 11.1 Create `examples/docker-compose/docker-compose.yml` with full stack: Octantis, mcp-grafana, Grafana, Prometheus, Loki, OTel Collector — all wired together with proper env vars and networking
- [x] 11.2 Create `examples/docker-compose/grafana/` provisioning files: Prometheus and Loki datasources auto-configured
- [x] 11.3 Create `examples/docker-compose/prometheus.yml` with scrape config for Octantis metrics endpoint
- [x] 11.4 Create `examples/docker-compose/otel-collector-config.yaml` exporting to Octantis OTLP receiver
- [x] 11.5 Create `examples/kubernetes/octantis.yaml` — Deployment + Service + ConfigMap with MCP env vars, Prometheus metrics port, and OTLP ports
- [x] 11.6 Create `examples/kubernetes/mcp-grafana.yaml` — Deployment + Service for mcp-grafana with Grafana API key Secret
- [x] 11.7 Create `examples/kubernetes/mcp-k8s.yaml` — Deployment + Service + ServiceAccount + RBAC for optional K8s MCP server
- [x] 11.8 Update `examples/README.md` documenting both deployment options (Docker Compose for local dev, Kubernetes for production) with required env vars and prerequisites
