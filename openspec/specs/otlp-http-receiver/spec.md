## ADDED Requirements

### Requirement: HTTP server accepts OTLP metrics via POST
The system SHALL expose an HTTP server on a configurable port (default 4318) that accepts POST requests on `/v1/metrics`. The server MUST support `application/json` and `application/x-protobuf` content types. On success, the system MUST return HTTP 200 with an empty body.

#### Scenario: Valid JSON metrics export
- **WHEN** an OTel Collector sends a POST to `/v1/metrics` with `Content-Type: application/json` and a valid OTLP JSON payload
- **THEN** the system parses the payload into an `InfraEvent` with `event_type="metric"`, enqueues it, and returns HTTP 200

#### Scenario: Valid Protobuf metrics export
- **WHEN** an OTel Collector sends a POST to `/v1/metrics` with `Content-Type: application/x-protobuf` and valid Protobuf data
- **THEN** the system parses the payload into an `InfraEvent`, enqueues it, and returns HTTP 200

### Requirement: HTTP server accepts OTLP logs via POST
The system SHALL accept POST requests on `/v1/logs` with `application/json` and `application/x-protobuf` content types. On success, the system MUST return HTTP 200 with an empty body.

#### Scenario: Valid logs export
- **WHEN** an OTel Collector sends a POST to `/v1/logs` with a valid OTLP payload
- **THEN** the system parses the payload into an `InfraEvent` with `event_type="log"`, enqueues it, and returns HTTP 200

### Requirement: HTTP server accepts traces for compatibility
The system SHALL accept POST requests on `/v1/traces` and return HTTP 200. The system MUST NOT parse or enqueue trace data. The system MUST log `otlp.trace.ignored` at DEBUG level.

#### Scenario: Trace export acknowledged and discarded via HTTP
- **WHEN** a POST is sent to `/v1/traces`
- **THEN** the system returns HTTP 200, does not enqueue any event, and logs `otlp.trace.ignored`

### Requirement: HTTP server returns 415 for unsupported content types
The system MUST return HTTP 415 (Unsupported Media Type) for requests with content types other than `application/json` and `application/x-protobuf`.

#### Scenario: Unsupported content type
- **WHEN** a POST is sent to `/v1/metrics` with `Content-Type: text/plain`
- **THEN** the system returns HTTP 415

### Requirement: HTTP server returns 404 for unknown paths
The system MUST return HTTP 404 for requests to any path other than `/v1/traces`, `/v1/metrics`, `/v1/logs`.

#### Scenario: Unknown path
- **WHEN** a POST is sent to `/v1/unknown`
- **THEN** the system returns HTTP 404

### Requirement: HTTP server handles parse errors gracefully
On malformed payloads, the system MUST log `otlp.parse.error` with a truncated raw payload (max 200 chars) and return HTTP 200. The system MUST NOT return error codes that trigger Collector retry loops.

#### Scenario: Malformed JSON payload
- **WHEN** a POST is sent to `/v1/metrics` with invalid JSON
- **THEN** the system logs `otlp.parse.error` and returns HTTP 200

### Requirement: HTTP port configurable via environment variable
The HTTP server MUST bind to the port specified by `OTLP_HTTP_PORT` (default 4318). If the port is already in use, the system MUST log `otlp.server.port_conflict` and exit with a non-zero code.

#### Scenario: Custom HTTP port
- **WHEN** `OTLP_HTTP_PORT` is set to 5318
- **THEN** the HTTP server binds to port 5318

### Requirement: HTTP transport disableable via environment variable
When `OTLP_HTTP_ENABLED` is set to `false`, the HTTP server MUST NOT be started. The system MUST log `otlp.http.disabled` at INFO level. The gRPC server (if enabled) MUST continue operating normally.

#### Scenario: HTTP disabled
- **WHEN** `OTLP_HTTP_ENABLED` is `false`
- **THEN** the HTTP server is not started, `otlp.http.disabled` is logged at INFO, and the gRPC server operates normally
