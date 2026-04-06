## Why

Octantis currently requires a Redpanda (Kafka-compatible) broker to receive telemetry events, but it is the sole consumer and final destination of the data. Running a distributed message broker for a single consumer adds operational complexity (provisioning, SASL config, topic/consumer group management) with zero architectural benefit. The OTel Collector already handles buffering and retries natively, making the broker redundant. The project is not in production, so this is the right time for a clean cut.

## What Changes

- **Add native OTLP gRPC receiver** (port 4317) implementing MetricsService, LogsService, and TraceService (traces accepted but discarded)
- **Add native OTLP HTTP receiver** (port 4318) with `/v1/metrics`, `/v1/logs`, `/v1/traces` endpoints
- **Add OTLP parser** that converts standard OTLP Protobuf/JSON payloads to existing `InfraEvent` Pydantic model, replacing the ad-hoc JSON parser in `consumers/redpanda.py`
- **Add `asyncio.Queue`-based bridge** between push-based receivers and the pull-based pipeline (`AsyncIterator[InfraEvent]`)
- **Add `OTLPSettings`** configuration via environment variables (`OTLP_GRPC_PORT`, `OTLP_HTTP_PORT`, `OTLP_GRPC_ENABLED`, `OTLP_HTTP_ENABLED`, `OTLP_QUEUE_MAX_SIZE`)
- **BREAKING**: Remove `RedpandaConsumer`, `RedpandaSettings`, and `aiokafka` dependency entirely
- **BREAKING**: Remove Redpanda from infrastructure requirements (Docker Compose, Kubernetes manifests)
- Update `main.py` to use `OTLPReceiver` instead of `RedpandaConsumer` (drop-in replacement preserving `start()`/`stop()`/`events()` interface)

## Capabilities

### New Capabilities
- `otlp-grpc-receiver`: gRPC server implementing OTLP MetricsService, LogsService, and TraceService (traces acknowledged but discarded)
- `otlp-http-receiver`: HTTP server accepting OTLP JSON and Protobuf payloads on standard `/v1/*` endpoints
- `otlp-parser`: Converts standard OTLP Protobuf/JSON payloads to `InfraEvent` using `opentelemetry-proto` package
- `otlp-receiver-orchestrator`: Orchestrates both servers + asyncio.Queue, exposes `events()` async iterator, handles graceful shutdown

### Modified Capabilities

_(none — no existing specs to modify)_

## Impact

- **Code**: New `src/octantis/receivers/` module (4 files). Modified `main.py` (~3 lines), `config.py` (add `OTLPSettings`, remove `RedpandaSettings`). Removed `consumers/redpanda.py`.
- **Dependencies**: Add `grpcio`, `opentelemetry-proto`, `aiohttp`. Remove `aiokafka`.
- **Infrastructure**: Redpanda removed from Docker Compose and K8s manifests. Octantis pod exposes ports 4317/4318. OTel Collector reconfigured to export directly to Octantis.
- **Documentation**: `docs/overview.md`, `docs/pipeline.md`, `README.md`, `AGENTS.md`, `.env.example` need updates.
- **Pipeline**: Downstream pipeline (PreFilter, EventBatcher, Sampler, LangGraph Workflow) is **unchanged** — the `InfraEvent` interface is preserved.
