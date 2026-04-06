# AGENTS.md — Octantis

## What This Project Is

An AI-powered infrastructure monitoring agent for EKS/Kubernetes. Receives OTel metrics/logs directly via OTLP (gRPC :4317 + HTTP :4318), uses an LLM to assess real operational severity, and notifies Slack + Discord with a concrete remediation plan.

## Essential Commands

```bash
uv sync                      # install dependencies (creates venv automatically)
uv run octantis               # run the agent
uv run pytest                 # run all tests
uv run pytest tests/test_pipeline.py -v   # specific test file
uv run pytest -k "prefilter" -v            # by keyword
uv run pytest -x              # stop on first failure

docker build -t octantis .    # build container image
```

No linting or formatting tools are configured. Python 3.12+ required. Package manager is `uv` with hatchling build backend.

## Architecture & Data Flow

```
OTel Collector → OTLP Receiver (gRPC/HTTP) → asyncio.Queue → PreFilter → EventBatcher → Sampler → LangGraph Workflow
                                                                                      │
                                                                                 collect (Prometheus + K8s API enrichment)
                                                                                      │
                                                                                 analyze (LLM: severity classification)
                                                                                      │
                                                                              [conditional: severity ≥ threshold?]
                                                                                      │
                                                                                 plan (LLM: remediation action plan)
                                                                                      │
                                                                                 notify (Slack + Discord)
```

The pipeline has three sequential filtering layers **before** any LLM call, designed to reduce cost by eliminating noise:

1. **PreFilter** (`pipeline/prefilter.py`) — Chain of Responsibility with 5 rules evaluated in order. First match wins. Fail-open default (no rule match → pass to LLM).
2. **EventBatcher** (`pipeline/batcher.py`) — Groups events by `namespace/workload` within a 30s window. Merges metrics (keeps latest value) and logs (keeps last 20).
3. **Sampler** (`pipeline/sampler.py`) — Suppresses duplicate fingerprints within a 5-minute sliding-window cooldown. LRU eviction at 1000 entries.

The LangGraph workflow (`graph/workflow.py`) is a compiled `StateGraph` with 4 nodes and one conditional edge after `analyze`. State is passed as `AgentState` (a `TypedDict, total=False`).

## Code Organization

```
src/octantis/
├── main.py              # Entry point: wires pipeline + consumer + workflow, runs async loop
├── config.py            # All config via Pydantic BaseSettings sub-models, singleton `settings`
├── receivers/
│   ├── receiver.py      # OTLPReceiver — orchestrates gRPC + HTTP + asyncio.Queue
│   ├── grpc_server.py   # gRPC servicer (MetricsService, LogsService, TraceService)
│   ├── http_server.py   # aiohttp server (/v1/metrics, /v1/logs, /v1/traces)
│   └── parser.py        # OTLP Protobuf/JSON → InfraEvent
├── collectors/
│   ├── prometheus.py    # Dynamic PromQL queries from event attributes
│   └── kubernetes.py    # K8s API: pod/node/deployment/events enrichment
├── pipeline/
│   ├── prefilter.py     # Rule-based filter chain (Protocol-based extensibility)
│   ├── batcher.py       # Time-window event grouping
│   └── sampler.py       # Fingerprint-based dedup with cooldown
├── graph/
│   ├── workflow.py      # LangGraph StateGraph definition, conditional edge
│   ├── state.py         # AgentState TypedDict
│   └── nodes/
│       ├── collector.py # Enrichment node: calls Prometheus + K8s collectors
│       ├── analyzer.py  # LLM node: severity classification via litellm
│       ├── planner.py   # LLM node: remediation plan generation via litellm
│       └── notifier.py  # Dispatches to Slack/Discord (fault-isolated)
├── notifiers/
│   ├── slack.py         # Block Kit formatting, webhook or Bot API
│   └── discord.py       # Embed formatting
└── models/
    ├── event.py         # InfraEvent, EnrichedEvent, PrometheusContext, KubernetesContext
    ├── analysis.py      # Severity enum, SeverityAnalysis
    └── action_plan.py   # ActionPlan, ActionStep, StepType enum
```

## Key Patterns & Conventions

- **Config**: All settings are environment variables mapped to `pydantic-settings` classes. The `settings` singleton at `config.py:140` is imported everywhere. Sub-models use `env_prefix` (e.g., `OTLP_`, `PIPELINE_`, `LLM_`). LLM API keys use `alias` since they don't share the prefix.
- **Async everywhere**: All I/O is async. Node functions are `async def`. Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio` decorators (they're present but not required).
- **State propagation**: Graph nodes return `{**state, "new_key": value}` — immutable merge, no in-place mutation of the incoming state dict.
- **Logging**: `structlog` everywhere. Logger obtained via `structlog.get_logger(__name__)`. Log events use dot-notation namespacing (e.g., `"octantis.batch.invoking_llm"`, `"prefilter.rule_matched"`). Console renderer when attached to a TTY, JSON renderer otherwise.
- **Models**: Pydantic v2 `BaseModel` for all data models. `Severity` and `StepType` are `str, Enum` for JSON serialization compatibility.
- **Error handling — fail-safe**: LLM parse errors in `analyzer` default to `MODERATE` severity (never silently drop). Planner parse errors produce a fallback "Manual investigation required" plan. Prometheus/K8s API failures set fields to `None` and continue. Notifier failures are isolated (Slack error doesn't block Discord).
- **PreFilter rules**: Implement the `Rule` protocol (`name: str` + `evaluate(event) -> FilterResult | None`). Return `None` to defer to the next rule. Order matters — `HealthCheckRule` first (cheapest, most frequent).

## Testing

- All tests use mocks — no real LLM calls, no external API calls.
- LLM node tests mock `litellm.acompletion` via `unittest.mock.patch`.
- Notifier tests mock both `settings` and the notifier classes.
- The `_event()` helper in `test_pipeline.py` is the standard way to build test `InfraEvent` objects.
- `EnrichedEvent.summary` is a `@property` that returns a string, not a method call.

## Gotchas & Non-Obvious Details

- **`EventBatcher._periodic_flush`** runs as a background `asyncio.Task`. It must be cancelled on shutdown — handled in the `finally` block of `batcher.run()`.
- **Sampler cooldown is a sliding window**: `last_seen` is updated even when an event is suppressed, so the cooldown resets on every duplicate. A persistent issue will never expire its cooldown until it stops occurring.
- **`_batch_key` priority**: `k8s_deployment_name > k8s_pod_name > service_name > source`. Two pods from the same Deployment in the same namespace share a batch — intentional, since they likely share a root cause.
- **`_fingerprint` is value-agnostic**: Only includes metric *names*, not values. `cpu=80%` and `cpu=95%` from the same pod produce the same fingerprint. Log body is truncated to `[:60]` to avoid minor message variations creating unique fingerprints.
- **`Severity` enum comparison** is done via `_SEVERITY_ORDER` dict mapping to ints (0-3), not enum ordering. The threshold comparison happens in `_should_notify()` in `workflow.py`.
- **`PrometheusCollector.collect`** is `async def` but uses the synchronous `prometheus_api_client.PrometheusConnect` internally. This blocks the event loop during HTTP calls — a known trade-off accepted for simplicity.
- **`_get_litellm_model`** is duplicated in both `analyzer.py` and `planner.py` (not shared).
- **OTLP parsing** in `receivers/parser.py` handles both Protobuf and JSON payloads via `opentelemetry-proto`. The parser uses `google.protobuf.json_format.ParseDict` to normalize JSON to Protobuf before processing.
- **`MetricThresholdRule` always-analyze names** (`oomkill`, `eviction`, `failed`, etc.) cause PASS regardless of metric value — even `container_oomkill_total=0` passes because the name indicates a problem class.
- **Empty `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL`** in `.env` disables the respective notifier — the `enabled` property checks truthiness.
- **`config.py:140`**: `settings = Settings()` is a module-level singleton, instantiated at import time. This means it reads `.env` on first import.
