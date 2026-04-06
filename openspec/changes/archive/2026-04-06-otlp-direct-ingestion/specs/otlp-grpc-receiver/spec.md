## ADDED Requirements

### Requirement: gRPC server implements OTLP MetricsService
The system SHALL expose a gRPC server on a configurable port (default 4317) that implements the `MetricsService` from `opentelemetry.proto.collector.metrics.v1`. The server MUST accept `ExportMetricsServiceRequest` in Protobuf format, parse it into `InfraEvent`, enqueue it, and return `ExportMetricsServiceResponse` with SUCCESS status.

#### Scenario: Valid metrics export
- **WHEN** an OTel Collector sends an `ExportMetricsServiceRequest` with gauge datapoints to gRPC port 4317
- **THEN** the system parses the payload into an `InfraEvent` with `event_type="metric"`, places it on the queue, and returns `ExportMetricsServiceResponse` with SUCCESS status

#### Scenario: Empty metrics payload
- **WHEN** an OTel Collector sends an `ExportMetricsServiceRequest` with a resource but no metrics
- **THEN** the system creates an `InfraEvent` with `event_type="unknown"`, `metrics=[]`, `logs=[]` and returns SUCCESS

### Requirement: gRPC server implements OTLP LogsService
The system SHALL implement the `LogsService` from `opentelemetry.proto.collector.logs.v1`. The server MUST accept `ExportLogsServiceRequest` in Protobuf format, parse it into `InfraEvent`, enqueue it, and return `ExportLogsServiceResponse` with SUCCESS status.

#### Scenario: Valid logs export
- **WHEN** an OTel Collector sends an `ExportLogsServiceRequest` with log records to gRPC port 4317
- **THEN** the system parses the payload into an `InfraEvent` with `event_type="log"`, places it on the queue, and returns `ExportLogsServiceResponse` with SUCCESS status

### Requirement: gRPC server implements OTLP TraceService for compatibility
The system SHALL implement `TraceService` from `opentelemetry.proto.collector.trace.v1`. The server MUST accept `ExportTraceServiceRequest` and return `ExportTraceServiceResponse` with SUCCESS status. The system MUST NOT parse or enqueue trace data. The system MUST log `otlp.trace.ignored` at DEBUG level.

#### Scenario: Trace export acknowledged and discarded
- **WHEN** an OTel Collector sends an `ExportTraceServiceRequest` to gRPC port 4317
- **THEN** the system returns SUCCESS, does not enqueue any event, and logs `otlp.trace.ignored` at DEBUG level

### Requirement: gRPC server handles parse errors gracefully
The system MUST catch parse errors at the servicer boundary. On malformed Protobuf or invalid data, the system MUST log `otlp.parse.error` with a truncated raw payload (max 200 chars) and return SUCCESS to the caller. The system MUST NOT crash or propagate exceptions.

#### Scenario: Malformed Protobuf payload
- **WHEN** a gRPC client sends a request with malformed Protobuf data
- **THEN** the system logs `otlp.parse.error`, returns SUCCESS, and does not crash

### Requirement: gRPC server always returns SUCCESS regardless of queue state
The system MUST return SUCCESS to the OTel Collector even when the queue is full or a parse error occurs. This prevents Collector retry storms.

#### Scenario: Queue full during gRPC export
- **WHEN** the queue has reached maxsize and a gRPC metrics export arrives
- **THEN** the system drops the event, logs `otlp.queue.dropped` with `reason="queue_full"`, and returns SUCCESS

### Requirement: gRPC port configurable via environment variable
The gRPC server MUST bind to the port specified by `OTLP_GRPC_PORT` (default 4317). If the port is already in use, the system MUST log `otlp.server.port_conflict` and exit with a non-zero code.

#### Scenario: Custom gRPC port
- **WHEN** `OTLP_GRPC_PORT` is set to 5317
- **THEN** the gRPC server binds to port 5317

#### Scenario: Port conflict on startup
- **WHEN** the configured gRPC port is already in use
- **THEN** the system logs `otlp.server.port_conflict` and exits with non-zero code

### Requirement: gRPC transport disableable via environment variable
When `OTLP_GRPC_ENABLED` is set to `false`, the gRPC server MUST NOT be started. The system MUST log `otlp.grpc.disabled` at INFO level. The HTTP server (if enabled) MUST continue operating normally.

#### Scenario: gRPC disabled
- **WHEN** `OTLP_GRPC_ENABLED` is `false`
- **THEN** the gRPC server is not started, `otlp.grpc.disabled` is logged at INFO, and the HTTP server operates normally
