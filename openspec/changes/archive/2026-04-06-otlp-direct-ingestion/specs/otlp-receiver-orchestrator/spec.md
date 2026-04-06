## ADDED Requirements

### Requirement: OTLPReceiver orchestrates gRPC and HTTP servers
The `OTLPReceiver` SHALL manage the lifecycle of both gRPC and HTTP servers and an `asyncio.Queue[InfraEvent]`. It MUST expose `start()`, `stop()`, and `events() → AsyncIterator[InfraEvent]` methods, matching the interface of the former `RedpandaConsumer`.

#### Scenario: Start both servers
- **WHEN** `OTLPReceiver.start()` is called with both transports enabled
- **THEN** the gRPC server starts on the configured port, the HTTP server starts on the configured port, and `otlp.server.started` is logged with `grpc_port`, `http_port`, `queue_max_size`

#### Scenario: events() yields from queue
- **WHEN** events are enqueued by gRPC and HTTP handlers and `events()` is iterated
- **THEN** it yields `InfraEvent` objects in FIFO order

### Requirement: Queue drops events when full
The `asyncio.Queue` MUST have a configurable `maxsize` (default 1000, via `OTLP_QUEUE_MAX_SIZE`). When full, new events MUST be dropped. The system MUST log `otlp.queue.dropped` with `reason="queue_full"`. Handlers MUST NOT block.

#### Scenario: Queue full
- **WHEN** the queue has reached maxsize and a new event arrives
- **THEN** the event is dropped, `otlp.queue.dropped` is logged, and the handler returns immediately

### Requirement: Queue high watermark warning
The system MUST log `otlp.queue.high_watermark` at WARNING level when queue size exceeds 50% of maxsize.

#### Scenario: Queue exceeds 50% capacity
- **WHEN** the queue size exceeds 500 (with default maxsize=1000)
- **THEN** `otlp.queue.high_watermark` is logged at WARNING level

### Requirement: Graceful shutdown
When `stop()` is called, the system MUST stop accepting new gRPC connections, stop the HTTP server, drain the queue of already-accepted events, and log `otlp.server.stopped`.

#### Scenario: Graceful stop drains queue
- **WHEN** `stop()` is called with events still in the queue
- **THEN** pending events are yielded from `events()` before the iterator ends, and `otlp.server.stopped` is logged

### Requirement: Both transports disabled
When both `OTLP_GRPC_ENABLED` and `OTLP_HTTP_ENABLED` are `false`, the system MUST log `otlp.server.no_transports` at WARNING level and start normally. The pipeline will receive no events.

#### Scenario: No transports enabled
- **WHEN** both `OTLP_GRPC_ENABLED` and `OTLP_HTTP_ENABLED` are `false`
- **THEN** the system logs `otlp.server.no_transports` at WARNING and starts without crashing

### Requirement: Concurrent gRPC and HTTP ingestion
The system MUST handle simultaneous events from both gRPC and HTTP transports. Both MUST write to the same shared `asyncio.Queue`.

#### Scenario: Concurrent gRPC and HTTP events
- **WHEN** one event arrives via gRPC and another via HTTP simultaneously
- **THEN** both events appear in the queue and are yielded by `events()`
