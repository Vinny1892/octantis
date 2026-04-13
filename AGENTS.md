# AGENTS.md — Octantis

## What This Project Is

An AI-powered infrastructure monitoring agent for **Kubernetes, Docker, and AWS**. Receives OTel metrics/logs directly via OTLP (gRPC :4317 + HTTP :4318), uses an LLM to assess real operational severity, and notifies Slack + Discord with a concrete remediation plan.

## Essential Commands

```bash
uv sync                      # install dependencies (creates venv automatically)
uv run octantis               # run the agent
uv run pytest                 # run all tests
uv run pytest tests/test_trigger_filter.py -v   # specific test file
uv run pytest tests/test_investigator.py -v     # investigator only
uv run pytest -k "cooldown" -v                  # by keyword
uv run pytest -x              # stop on first failure

docker build -t octantis .    # build container image
```

No linting or formatting tools are configured. Python 3.12+ required. Package manager is `uv` with hatchling build backend.

**Runtime mode** (Phase 4): `OCTANTIS_MODE=standalone` (default) runs all workflows concurrently in one process, bounded by `OCTANTIS_WORKERS` (default 20). Modes `ingester` and `worker` (Redpanda-based) are Phase 5.

## Architecture & Data Flow

```
OTel Collector → OTLP Ingester (gRPC/HTTP) → asyncio.Queue → TriggerFilter → FingerprintCooldown → EnvironmentDetector → LangGraph Workflow
                                                                                                                              │
                                                                                                    investigate (ReAct loop via MCP tools)
                                                                                                                              │
                                                                                                    analyze (LLM: severity classification)
                                                                                                                              │
                                                                                                    [conditional: severity ≥ threshold?]
                                                                                                                              │
                                                                                                    plan (LLM: remediation action plan)
                                                                                                                              │
                                                                                                    notify (Slack + Discord)
```

The pipeline has three sequential filtering/detection layers **before** any LLM call:

1. **TriggerFilter** (`pipeline/trigger_filter.py`) — Chain of Responsibility with 5 rules evaluated in order. First match wins. Fail-open default (no rule match → pass to LLM). Supports Node Exporter host-level metrics (`node_cpu`, `node_memory`, `node_filesystem`, `node_network`).
2. **FingerprintCooldown** (`pipeline/cooldown.py`) — Suppresses duplicate fingerprints within a 5-minute sliding-window cooldown. LRU eviction at 1000 entries.
3. **EnvironmentDetector** (`pipeline/environment_detector.py`) — Promotes base `OTelResource` to typed subclass (`K8sResource`, `DockerResource`, `AWSResource`) based on OTLP resource attributes or `OCTANTIS_PLATFORM` override.

The LangGraph workflow (`graph/workflow.py`) is a compiled `StateGraph` with 4 nodes and one conditional edge after `analyze`. State is passed as `AgentState` (a `TypedDict, total=False`).

## Code Organization

```
src/octantis/
├── main.py              # Entry point: discovers plugins via registry, wires pipeline + MCP, runs async loop
├── config.py            # All config via Pydantic BaseSettings sub-models, singleton `settings`
├── metrics.py           # Prometheus metrics + HTTP server
├── receivers/           # Transport layer (shared by ingester plugins)
│   ├── grpc_server.py   # gRPC servicer (MetricsService, LogsService, TraceService) → SDK Event
│   ├── http_server.py   # aiohttp server (/v1/metrics, /v1/logs, /v1/traces) → SDK Event
│   └── parser.py        # OTLP Protobuf/JSON → SDK Event (includes counter normalization)
├── pipeline/
│   ├── trigger_filter.py       # Rule-based filter chain (Protocol-based extensibility)
│   ├── cooldown.py             # Fingerprint-based dedup with cooldown
│   └── environment_detector.py # Platform detection: K8s / Docker / AWS
├── mcp_client/
│   ├── manager.py       # MCPClientManager — single-server connect + retry
│   └── aggregator.py    # AggregatedMCPManager — facade over multiple per-server MCPConnectors
├── plugins/
│   ├── registry.py      # PluginRegistry — entry-point discovery, fixed load order, lifecycle
│   └── builtins/
│       ├── ingester_plugins.py       # Ingester adapters: OTLPGrpcIngester + OTLPHttpIngester
│       ├── trigger_filter_plugin.py  # Processor adapter: TriggerFilter (priority 100)
│       ├── cooldown_plugin.py        # Processor adapter: FingerprintCooldown (priority 200)
│       ├── notifier_plugins.py       # Notifier adapters: Slack + Discord
│       └── mcp_plugins.py            # MCPConnector adapters: Grafana, K8s, Docker, AWS
├── graph/
│   ├── workflow.py      # LangGraph StateGraph definition, conditional edge
│   ├── state.py         # AgentState TypedDict
│   └── nodes/
│       ├── investigator.py  # Node: ReAct loop with MCP tools (platform-aware prompt)
│       ├── analyzer.py      # Node: LLM classifies severity via litellm
│       ├── planner.py       # Node: LLM generates remediation plan via litellm
│       └── notifier.py      # Node: Dispatches to Slack/Discord (fault-isolated)
├── notifiers/
│   ├── slack.py         # Block Kit formatting, webhook or Bot API
│   └── discord.py       # Embed formatting
└── models/
    ├── event.py         # OTelResource hierarchy, InfraEvent, InvestigationResult, MCPQueryRecord
    ├── analysis.py      # Severity enum, SeverityAnalysis
    └── action_plan.py   # ActionPlan, ActionStep, StepType enum
```

## Key Patterns & Conventions

- **Config**: All settings are environment variables mapped to `pydantic-settings` classes. The `settings` singleton at `config.py` is imported everywhere. Sub-models use `env_prefix` (e.g., `OTLP_`, `PIPELINE_`, `LLM_`, `DOCKER_MCP_`, `AWS_MCP_`). LLM API keys use `alias` since they don't share the prefix.
- **OTelResource hierarchy**: Base `OTelResource` with common fields (`service_name`, `host_name`, `extra`). Subclasses: `K8sResource` (K8s fields), `DockerResource` (container fields), `AWSResource` (cloud fields). Each implements `context_summary() -> str` for polymorphic LLM prompts.
- **MCP slot model**: `MCPClientManager` accepts `list[MCPServerConfig]` with `name`, `slot` (observability/platform), `url`, `headers`. Validates min 1 total, max 1 per slot. Connects generically via `_connect_server()` with exponential backoff retry.
- **Async everywhere**: All I/O is async. Node functions are `async def`. Tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- **State propagation**: Graph nodes return `{**state, "new_key": value}` — immutable merge, no in-place mutation.
- **Logging**: `structlog` everywhere. Console renderer when TTY, JSON renderer otherwise.
- **Models**: Pydantic v2 `BaseModel` for all data models. `Severity` and `StepType` are `str, Enum`.
- **Error handling — fail-safe**: LLM parse errors default to `MODERATE` severity. Planner parse errors produce fallback plan. MCP failures enter degraded mode. Notifier failures are isolated.
- **TriggerFilter rules**: Implement the `Rule` protocol (`name: str` + `evaluate(event) -> FilterResult | None`). Return `None` to defer. Supports both pod-level metrics and Node Exporter host-level metrics.

## Testing

- All tests use mocks — no real LLM calls, no external API calls.
- LLM node tests mock `litellm.acompletion` via `unittest.mock.patch`.
- MCP client tests mock `sse_client`, `ClientSession`, and `load_mcp_tools`.
- Investigator tests cover K8s, Docker, and AWS trigger contexts.
- The `MCPClientManager` tests cover slot validation, retry success, and retry exhaustion.
- `InvestigationResult.summary` is a `@property` that delegates to `resource.context_summary()`.

## Plugin Architecture (Phase 1–2 landed)

The `Plugin Registry` at `src/octantis/plugins/registry.py` discovers components
via Python entry points and drives their lifecycle. The stable public contract
for plugin authors lives in the separate Apache-2.0 package
`packages/octantis-plugin-sdk/` (6 Protocols + shared types).

- Entry-point groups (frozen once published): `octantis.ingesters`,
  `octantis.storage`, `octantis.mcp`, `octantis.processors`, `octantis.notifiers`,
  `octantis.ui`. (Octantis uses **"Ingester"** to distinguish its event-source
  Protocol from the OTel Collector's "receiver" pipeline stage.)
- Fixed load order: Ingesters → Storage → MCP → Processors → Notifiers → UI.
  Processors further sorted by integer `priority` (lower first).
- `main.py` wires **everything** via the registry — no direct component imports.
  Ingesters, processors, MCP connector, and notifiers (Slack, Discord)
  are all discovered via entry points and run through their Protocol adapters.
- Built-in plugins (all registered in `pyproject.toml`):
  - `otlp-grpc`, `otlp-http` (ingesters) — `plugins/builtins/ingester_plugins.py`
  - `trigger-filter` (priority 100) — `plugins/builtins/trigger_filter_plugin.py`
  - `fingerprint-cooldown` (priority 200) — `plugins/builtins/cooldown_plugin.py`
  - `grafana-mcp`, `k8s-mcp`, `docker-mcp`, `aws-mcp` — `plugins/builtins/mcp_plugins.py`
  - `slack`, `discord` — `plugins/builtins/notifier_plugins.py`
- **Ingester Protocol**: Event sources (OTLP gRPC/HTTP, pull scrapers, tailers). Methods: `setup()`, `teardown()`, `start()`, `stop()`, `events()`.
- **Storage Protocol**: Persistence backends (future). Methods: `setup()`, `teardown()`, `save_investigation()`, `is_cooled_down()`.
- Full contributor guide: `docs/plugins.md`. Tech Spec:
  `docs/tech-specs/tech-spec-005-plugin-architecture.md`. Active change:
  `openspec/changes/implement-plugin-architecture/`.

## Gotchas & Non-Obvious Details

- **`_fingerprint` uses `extra` dict**: Reads K8s attributes from `resource.extra` (before environment detection), falling back to `event.source` for non-K8s events.
- **`EnvironmentDetector` creates new events**: Returns `event.model_copy(update={"resource": promoted})` — does not mutate the original.
- **EKS dual-attribute priority**: K8s detection takes priority over AWS (rule 2 before rule 4). Use `OCTANTIS_PLATFORM=aws` to override for EKS if needed.
- **Counter normalization**: Parser normalizes known Node Exporter counters (e.g., `node_cpu_seconds_total`) to percentages before building the SDK Event metrics list. Unknown counters pass through unchanged.
- **SDK Event boundary**: `OTLPParser` emits `octantis_plugin_sdk.Event` (flat dicts for `resource`, `metrics`, `logs`). The internal workflow layer uses `InfraEvent` with typed `OTelResource`; `main.py` converts via `_sdk_to_infra_event()` after the processor chain.
- **Standalone concurrency**: `_run_standalone()` uses `asyncio.TaskGroup` + `asyncio.Semaphore(OCTANTIS_WORKERS)`. Each event spawns a task; the semaphore caps parallel investigation workflows. `TaskGroup` propagates cancellation cleanly on shutdown.
- **`OCTANTIS_WORKERS`**: default 20. Tune based on LLM call latency and desired throughput. Too high → rate-limit errors from the LLM provider. Too low → event backlog in queue.
- **Slot validation is immediate**: `MCPClientManager.validate_slots()` runs at the start of `connect()`, before any network call. Zero MCPs or duplicate slots raise `SlotValidationError`.
- **Retry clears degraded state**: If a connection fails then succeeds on retry, the server is removed from `_degraded_servers`.
- **`MCPQueryRecord.datasource`** accepts `"promql"`, `"logql"`, `"k8s"`, `"docker"`, and `"aws"` — classified by tool name pattern in `_classify_datasource()`.
- **`MetricThresholdRule`** recognizes `node_cpu`, `node_memory`, `node_filesystem`, `node_network` prefixes alongside standard pod-level metrics.
- **`config.py`**: `settings = Settings()` is a module-level singleton, instantiated at import time.
- **Cooldown sliding window**: `last_seen` is updated even on suppressed events, so persistent issues renew the cooldown.
