## Context

Octantis consumes telemetry via `RedpandaConsumer` (aiokafka) from a Kafka-compatible broker. The data flow is: OTel Collector → Redpanda → aiokafka consumer → `_parse_otel_message()` → `InfraEvent` → Pipeline. The downstream pipeline (`PreFilter → EventBatcher → Sampler → LangGraph Workflow`) consumes an `AsyncIterator[InfraEvent]` from `main.py`.

The project is single-developer, pre-production, and Octantis is the sole consumer. Redpanda provides no fan-out, replay, or multi-consumer benefit.

## Goals / Non-Goals

**Goals:**
- Expose native OTLP endpoints (gRPC :4317, HTTP :4318) so OTel Collectors export directly to Octantis
- Parse standard OTLP Protobuf/JSON using `opentelemetry-proto` (replacing ad-hoc JSON parsing)
- Preserve the `start()`/`stop()`/`events() → AsyncIterator[InfraEvent]` interface so `main.py` changes are minimal
- Remove Redpanda, `aiokafka`, and `RedpandaSettings` completely

**Non-Goals:**
- Persistent event buffer or retry queue (event loss accepted by design)
- Authentication or TLS on OTLP endpoints in v1
- Changes to the filtering pipeline or LangGraph Workflow
- Trace processing (traces are acknowledged but discarded)
- Forwarding events to other consumers

## Decisions

### Decision 1: asyncio.Queue as receiver-pipeline bridge

The gRPC and HTTP servers are push-based (request handlers), while the pipeline expects a pull-based `AsyncIterator[InfraEvent]`. An `asyncio.Queue[InfraEvent]` owned by `OTLPReceiver` bridges this gap. Server handlers call `queue.put_nowait(event)`; `OTLPReceiver.events()` yields from the queue.

**Alternatives considered:**
- Direct callback to pipeline — rejected: couples receiver to pipeline internals, no backpressure
- AsyncIterator protocol on receiver — rejected: hard to implement cleanly with push-based handlers

### Decision 2: Drop-on-full queue (maxsize=1000)

When the queue is full, new events are dropped and logged (`otlp.queue.dropped`). Handlers always return SUCCESS/200 to the caller. Queue maxsize configurable via `OTLP_QUEUE_MAX_SIZE`.

**Alternatives considered:**
- Block-on-full — rejected: blocks gRPC/HTTP workers, stalls OTel Collector
- Unbounded queue — rejected: OOM risk on sustained slow pipeline

### Decision 3: grpcio (grpc.aio) + opentelemetry-proto + aiohttp

Use `grpcio` with `grpc.aio` async servicers for gRPC, `aiohttp` for HTTP, and `opentelemetry-proto` for all Protobuf message types.

**Alternatives considered:**
- `grpclib` — rejected: less adoption, not used by OTel Python ecosystem
- FastAPI/uvicorn for HTTP — rejected: heavy dependency for 3 simple endpoints; aiohttp is sufficient

### Decision 4: OTLPReceiver as drop-in for RedpandaConsumer

`OTLPReceiver` exposes `start()`, `stop()`, `events() → AsyncIterator[InfraEvent]` — same interface as `RedpandaConsumer`. Changes in `main.py` are limited to import path and instantiation (~3 lines).

### Decision 5: Traces accepted but not processed

Octantis only analyzes metrics and logs. TraceService (gRPC) and `/v1/traces` (HTTP) return SUCCESS/200 but do not parse or enqueue trace data. This avoids breaking OTel Collector pipelines that export all signal types.

### Decision 6: Per-transport enable flags

`OTLP_GRPC_ENABLED` and `OTLP_HTTP_ENABLED` (both default true) give operators fine-grained control. If both disabled, Octantis starts normally but logs a warning.

## Risks / Trade-offs

- **Events lost in queue on crash** → Accepted by design. New events arrive when agent recovers.
- **Events dropped when pipeline is slow** → Queue drop-on-full with logging. PRD explicitly accepts event loss.
- **OTLP Protobuf parsing more complex than ad-hoc JSON** → Mitigated by using official `opentelemetry-proto` package with pre-generated Python classes.
- **Breaking change if OTLP → InfraEvent mapping diverges from current parser** → Write comparative tests against old parser before removing it.
- **No authentication in v1** → Trust boundary is cluster network. Add mTLS later if endpoint becomes externally reachable.

## Migration Plan

1. **Phase 1 — Implement receiver**: Add `src/octantis/receivers/` module. Unit tests for parser. Comparative tests against old parser.
2. **Phase 2 — Integrate & remove Redpanda**: Update `main.py` and `config.py`. Remove `consumers/redpanda.py` and `aiokafka`. Update Docker Compose / K8s manifests.
3. **Phase 3 — Documentation**: Update docs, README, AGENTS.md, .env.example.

Rollback: `git revert` integration commit; restart Redpanda if needed.

## Open Questions

_(none — all decisions resolved in PRD and tech spec)_
