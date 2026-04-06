## 1. Project Setup

- [x] 1.1 Add `grpcio`, `grpcio-tools`, `opentelemetry-proto`, `aiohttp` to `pyproject.toml` dependencies
- [x] 1.2 Create `src/octantis/receivers/` package with `__init__.py`
- [x] 1.3 Add `OTLPSettings` to `config.py` (`OTLP_GRPC_PORT`, `OTLP_HTTP_PORT`, `OTLP_GRPC_ENABLED`, `OTLP_HTTP_ENABLED`, `OTLP_QUEUE_MAX_SIZE`)

## 2. OTLP Parser

- [x] 2.1 Implement `receivers/parser.py` — `OTLPParser` class with `parse_metrics_proto()`, `parse_logs_proto()`, `parse_metrics_json()`, `parse_logs_json()` methods converting OTLP payloads to `InfraEvent`
- [x] 2.2 Implement resource attribute mapping to `OTelResource` (known fields + `extra` dict)
- [x] 2.3 Implement `event_id` UUID4 generation, `event_type` inference, and `source` fallback
- [x] 2.4 Write unit tests `tests/test_parser.py` — valid metrics/logs (Protobuf + JSON), resource mapping, empty payload, malformed input, event_id generation, source fallback

## 3. gRPC Receiver

- [x] 3.1 Implement `receivers/grpc_server.py` — async gRPC servicer for `MetricsService`, `LogsService`, `TraceService` using `grpc.aio`
- [x] 3.2 Implement queue put_nowait with QueueFull handling and structured logging (`otlp.grpc.received`, `otlp.queue.dropped`, `otlp.trace.ignored`, `otlp.parse.error`)
- [x] 3.3 Write unit tests for gRPC servicer — valid export, trace ignored, parse error handling, queue full behavior

## 4. HTTP Receiver

- [x] 4.1 Implement `receivers/http_server.py` — aiohttp server with routes for `/v1/metrics`, `/v1/logs`, `/v1/traces`
- [x] 4.2 Implement content-type validation (JSON + Protobuf), 415 for unsupported types, 404 for unknown paths
- [x] 4.3 Implement queue put_nowait with structured logging (`otlp.http.received`, `otlp.queue.dropped`, `otlp.trace.ignored`, `otlp.parse.error`)
- [x] 4.4 Write unit tests for HTTP server — valid JSON/Protobuf export, trace ignored, 415 unsupported type, 404 unknown path, parse error handling

## 5. Receiver Orchestrator

- [x] 5.1 Implement `receivers/__init__.py` — `OTLPReceiver` class with `start()`, `stop()`, `events() → AsyncIterator[InfraEvent]`, managing both servers + `asyncio.Queue`
- [x] 5.2 Implement transport enable/disable logic (`OTLP_GRPC_ENABLED`, `OTLP_HTTP_ENABLED`) with appropriate logging
- [x] 5.3 Implement graceful shutdown — stop servers, drain queue, log `otlp.server.stopped`
- [x] 5.4 Implement queue high watermark warning (`otlp.queue.high_watermark` at >50% capacity)
- [x] 5.5 Write unit tests `tests/test_otlp_receiver.py` — queue put/drop, events() iteration, graceful stop drain, both transports disabled warning

## 6. Integration & Redpanda Removal

- [x] 6.1 Update `main.py` — replace `RedpandaConsumer` with `OTLPReceiver`, update imports and instantiation
- [x] 6.2 Remove `consumers/redpanda.py` and any imports referencing it
- [x] 6.3 Remove `RedpandaSettings` from `config.py`
- [x] 6.4 Remove `aiokafka` from `pyproject.toml`
- [x] 6.5 Update `.env.example` with OTLP environment variables, remove Redpanda variables
- [x] 6.6 Update `Dockerfile` — remove Redpanda references, expose ports 4317/4318

## 7. Integration Tests

- [x] 7.1 Write `tests/test_otlp_integration.py` — gRPC round-trip (send ExportMetricsServiceRequest via grpc.aio channel, verify InfraEvent from events())
- [x] 7.2 Write HTTP round-trip integration test (POST OTLP JSON to /v1/metrics via aiohttp client, verify InfraEvent)
- [x] 7.3 Write concurrent gRPC + HTTP test — simultaneous events from both transports appear in queue
- [x] 7.4 Write transport disabled integration test — gRPC disabled, only HTTP running
- [x] 7.5 Create test fixtures: `fixtures/otlp_metrics.pb`, `fixtures/otlp_logs.pb`, `fixtures/otlp_metrics.json`, `fixtures/otlp_logs.json`
- [x] 7.6 Run full test suite (`uv run pytest`) and verify all tests pass

## 8. Documentation

- [x] 8.1 Update `docs/overview.md` — replace Redpanda architecture with OTLP receiver
- [x] 8.2 Update `docs/pipeline.md` — reflect new ingestion path
- [x] 8.3 Update `README.md` — quickstart without Redpanda, new ports
- [x] 8.4 Update `AGENTS.md` — reflect new module structure
