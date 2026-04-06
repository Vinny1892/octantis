## MODIFIED Requirements

### Requirement: OTLPReceiver orchestrates gRPC and HTTP servers
The `OTLPReceiver` SHALL manage the lifecycle of both gRPC and HTTP servers and an `asyncio.Queue[InfraEvent]`. It MUST expose `start()`, `stop()`, and `events() → AsyncIterator[InfraEvent]` methods, matching the interface of the former `RedpandaConsumer`.

#### Scenario: Start both servers
- **WHEN** `OTLPReceiver.start()` is called with both transports enabled
- **THEN** the gRPC server starts on the configured port, the HTTP server starts on the configured port, and `otlp.server.started` is logged with `grpc_port`, `http_port`, `queue_max_size`

#### Scenario: events() yields from queue
- **WHEN** events are enqueued by gRPC and HTTP handlers and `events()` is iterated
- **THEN** it yields `InfraEvent` objects in FIFO order

#### Scenario: Main loop uses TriggerFilter and Cooldown instead of Batcher and Sampler
- **WHEN** the main loop processes events from the OTLP receiver
- **THEN** events flow through TriggerFilter → FingerprintCooldown → workflow (investigate → analyze → plan → notify) without any EventBatcher or Sampler
