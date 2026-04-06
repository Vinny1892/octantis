## ADDED Requirements

### Requirement: Parse OTLP metrics Protobuf to InfraEvent
The system SHALL parse `ExportMetricsServiceRequest` Protobuf payloads into `InfraEvent` objects. Resource attributes MUST be mapped to `OTelResource` fields. ScopeMetrics gauge/sum datapoints MUST be mapped to `MetricDataPoint` entries. The resulting `InfraEvent` MUST have `event_type="metric"`.

#### Scenario: Metrics with gauge datapoints
- **WHEN** the parser receives an `ExportMetricsServiceRequest` with 2 gauge datapoints
- **THEN** it returns an `InfraEvent` with `event_type="metric"` and 2 `MetricDataPoint` entries with correct name, value, and unit

### Requirement: Parse OTLP logs Protobuf to InfraEvent
The system SHALL parse `ExportLogsServiceRequest` Protobuf payloads into `InfraEvent` objects. ScopeLogs logRecords MUST be mapped to `LogRecord` entries with `body` (from `body.stringValue`), `severity_text`, and `severity_number`. The resulting `InfraEvent` MUST have `event_type="log"`.

#### Scenario: Logs with severity
- **WHEN** the parser receives an `ExportLogsServiceRequest` with 1 log record (severity_text="ERROR")
- **THEN** it returns an `InfraEvent` with `event_type="log"` and 1 `LogRecord` entry with correct body, severity_text, and severity_number

### Requirement: Parse OTLP JSON payloads
The system SHALL parse OTLP JSON payloads (`resourceMetrics` / `resourceLogs`) into the same `InfraEvent` format as Protobuf. JSON and Protobuf inputs with equivalent data MUST produce identical `InfraEvent` output.

#### Scenario: JSON metrics produce same output as Protobuf
- **WHEN** the parser receives an OTLP JSON payload with `resourceMetrics`
- **THEN** it returns an `InfraEvent` identical to the one produced from the equivalent Protobuf payload

### Requirement: Map resource attributes to OTelResource
The parser MUST map standard OTLP resource attributes to `OTelResource` fields: `service.name` → `service_name`, `service.namespace` → `service_namespace`, `k8s.namespace.name` → `k8s_namespace`, `k8s.pod.name` → `k8s_pod_name`, `k8s.node.name` → `k8s_node_name`, `k8s.deployment.name` → `k8s_deployment_name`. All other resource attributes MUST be stored in `OTelResource.extra` dict.

#### Scenario: Known resource attributes mapped
- **WHEN** the parser receives a payload with `service.name`, `k8s.namespace.name`, `k8s.pod.name`
- **THEN** the `OTelResource` has `service_name`, `k8s_namespace`, `k8s_pod_name` populated correctly

#### Scenario: Unknown resource attributes stored in extra
- **WHEN** the parser receives a payload with an unknown attribute `custom.label`
- **THEN** the `OTelResource.extra` dict contains `{"custom.label": <value>}`

### Requirement: Generate event_id as UUID4
The parser MUST generate `event_id` as a UUID4 string for every `InfraEvent`. OTLP has no concept of event ID.

#### Scenario: event_id is valid UUID4
- **WHEN** the parser creates an `InfraEvent` from any valid payload
- **THEN** the `event_id` field is a valid UUID4 string

### Requirement: Infer event_type from payload content
The parser MUST set `event_type` to `"metric"` if metrics are present, `"log"` if logs are present, and `"unknown"` if neither metrics nor logs are present.

#### Scenario: Payload with only resource (no metrics or logs)
- **WHEN** the parser receives a payload with a resource but no metrics and no logs
- **THEN** the `InfraEvent` has `event_type="unknown"`, `metrics=[]`, `logs=[]`

### Requirement: Source fallback to "unknown"
The parser MUST set `InfraEvent.source` to `resource.service_name` if present, otherwise `"unknown"`.

#### Scenario: Missing service.name
- **WHEN** the parser receives a payload without `service.name` in resource attributes
- **THEN** the `InfraEvent` has `source="unknown"`

### Requirement: Return None on parse failure
On malformed Protobuf or invalid JSON, the parser MUST return `None` and MUST NOT raise exceptions. Error logging is the caller's responsibility.

#### Scenario: Malformed Protobuf
- **WHEN** the parser receives garbage bytes as Protobuf
- **THEN** it returns `None` without raising an exception

#### Scenario: Invalid JSON
- **WHEN** the parser receives an invalid JSON string
- **THEN** it returns `None` without raising an exception
