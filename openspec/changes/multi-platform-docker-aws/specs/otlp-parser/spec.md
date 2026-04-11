## MODIFIED Requirements

### Requirement: Parse OTLP metrics Protobuf to InfraEvent
The system SHALL parse `ExportMetricsServiceRequest` Protobuf payloads into `InfraEvent` objects. Resource attributes MUST be mapped to `OTelResource` fields. ScopeMetrics gauge/sum datapoints MUST be mapped to `MetricDataPoint` entries. The resulting `InfraEvent` MUST have `event_type="metric"`. For known Node Exporter counter metrics, the parser MUST normalize counter values to percentages before storing in `MetricDataPoint.value`.

#### Scenario: Metrics with gauge datapoints
- **WHEN** the parser receives an `ExportMetricsServiceRequest` with 2 gauge datapoints
- **THEN** it returns an `InfraEvent` with `event_type="metric"` and 2 `MetricDataPoint` entries with correct name, value, and unit

#### Scenario: Node Exporter CPU counter normalized
- **WHEN** the parser receives a metric named `node_cpu_seconds_total` with value `123456.78`
- **THEN** the parser normalizes the value to a CPU usage percentage (value modulo 1.0 × 100, capped at 100.0)
- **AND** stores the normalized value in `MetricDataPoint.value`
- **AND** preserves the original metric name `node_cpu_seconds_total`

#### Scenario: Node Exporter memory metric normalized
- **WHEN** the parser receives a metric named `node_memory_MemAvailable_bytes` with value `2147483648`
- **THEN** the parser passes the value through unchanged (gauge, not a counter requiring normalization)

#### Scenario: Unknown counter metric passes through
- **WHEN** the parser receives a metric name not in the known Node Exporter counter list
- **THEN** the parser passes the value through unchanged with no normalization
- **AND** MUST NOT raise an error

## ADDED Requirements

### Requirement: Node Exporter counter normalization map
The parser SHALL maintain a mapping of known Node Exporter counter metric name patterns to normalization strategies. The map MUST include at minimum: `node_cpu_seconds_total` (normalize to CPU %), `node_filesystem_avail_bytes` (no normalization, gauge), `node_network_receive_errs_total` (pass-through counter).

#### Scenario: Normalization map covers key metrics
- **WHEN** the parser encounters a metric named `node_cpu_seconds_total`
- **THEN** the normalization map contains an entry for it and applies the CPU percentage normalization

#### Scenario: Metric name matches node_ prefix but is unknown
- **WHEN** the parser encounters a metric starting with `node_` that is not in the normalization map
- **THEN** the value passes through unchanged

### Requirement: Parser logs counter normalization
The parser MUST log `parser.counter_normalized` at DEBUG level when a counter metric is normalized, including the metric name, raw value, and normalized value.

#### Scenario: Normalization logged
- **WHEN** the parser normalizes `node_cpu_seconds_total` from `123456.78` to `56.78`
- **THEN** it logs `parser.counter_normalized` with `metric_name`, `raw_value`, and `normalized_value`
