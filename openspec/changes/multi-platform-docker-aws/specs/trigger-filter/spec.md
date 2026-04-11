## MODIFIED Requirements

### Requirement: TriggerFilter detects anomalous events
The `TriggerFilter` SHALL evaluate incoming OTLP events against a set of rules and decide whether the event warrants LLM investigation. It MUST detect: anomalous metric values (CPU, memory, error rate above thresholds), elevated log severity (ERROR, FATAL, WARNING), known critical patterns (OOMKill, CrashLoopBackOff, eviction, panic, timeout), AND Node Exporter host-level metrics (`node_cpu`, `node_memory`, `node_filesystem`, `node_network` prefixes).

#### Scenario: High CPU triggers investigation
- **WHEN** an event contains a CPU metric at 85% and the threshold is 75%
- **THEN** the TriggerFilter returns PASS with reason indicating the threshold breach

#### Scenario: Error log triggers investigation
- **WHEN** an event contains a log with severity_text "ERROR"
- **THEN** the TriggerFilter returns PASS with reason indicating the log severity

#### Scenario: Critical pattern triggers investigation
- **WHEN** an event contains a metric named "container_oomkill_total"
- **THEN** the TriggerFilter returns PASS with reason indicating the critical pattern

#### Scenario: Node Exporter CPU metric triggers investigation
- **WHEN** an event contains a metric named `node_cpu_seconds_total` with normalized value 85% and CPU threshold is 75%
- **THEN** the TriggerFilter returns PASS with reason `"threshold breached: node_cpu_seconds_total=85.0%"`

#### Scenario: Node Exporter memory metric triggers investigation
- **WHEN** an event contains a metric named `node_memory_MemAvailable_bytes` with value indicating memory usage above 80% threshold
- **THEN** the TriggerFilter returns PASS with reason indicating memory threshold breach

#### Scenario: Node Exporter metric below threshold dropped
- **WHEN** an event contains only Node Exporter metrics with all values below their thresholds
- **THEN** the TriggerFilter returns DROP with reason `"all metrics within normal thresholds"`

#### Scenario: Both K8s and Node Exporter metrics present
- **WHEN** an event has both a K8s CPU metric at 30% and a Node Exporter CPU metric at 90%
- **THEN** the TriggerFilter returns PASS because the Node Exporter metric exceeds the threshold

### Requirement: MetricThresholdRule recognizes Node Exporter metric names
The `MetricThresholdRule` MUST recognize metric names starting with `node_cpu`, `node_memory`, `node_filesystem`, and `node_network` as host-level metrics. It MUST apply the same threshold defaults (CPU 75%, memory 80%) to these metrics. It MUST also recognize metric names containing `node_network` with error-related suffixes (e.g., `node_network_receive_errs_total`) as always-analyze metrics.

#### Scenario: node_cpu metric evaluated against CPU threshold
- **WHEN** a metric named `node_cpu_seconds_total` has normalized value 80%
- **THEN** it is evaluated against `cpu_ok_below` threshold (default 75%) and triggers PASS

#### Scenario: node_filesystem metric evaluated against memory threshold
- **WHEN** a metric named `node_filesystem_avail_bytes` has value indicating disk usage above 80%
- **THEN** it triggers PASS with filesystem threshold breach

#### Scenario: node_network error metric always analyzed
- **WHEN** a metric named `node_network_receive_errs_total` is present with any value
- **THEN** the TriggerFilter returns PASS due to the "error" keyword in the metric name matching always-analyze names
