## ADDED Requirements

### Requirement: TriggerFilter detects anomalous events
The `TriggerFilter` SHALL evaluate incoming OTLP events against a set of rules and decide whether the event warrants LLM investigation. It MUST detect: anomalous metric values (CPU, memory, error rate above thresholds), elevated log severity (ERROR, FATAL, WARNING), and known critical patterns (OOMKill, CrashLoopBackOff, eviction, panic, timeout).

#### Scenario: High CPU triggers investigation
- **WHEN** an event contains a CPU metric at 85% and the threshold is 75%
- **THEN** the TriggerFilter returns PASS with reason indicating the threshold breach

#### Scenario: Error log triggers investigation
- **WHEN** an event contains a log with severity_text "ERROR"
- **THEN** the TriggerFilter returns PASS with reason indicating the log severity

#### Scenario: Critical pattern triggers investigation
- **WHEN** an event contains a metric named "container_oomkill_total"
- **THEN** the TriggerFilter returns PASS with reason indicating the critical pattern

### Requirement: TriggerFilter drops health check probes
The TriggerFilter MUST drop events that match health check probe patterns (GET /health, GET /healthz, GET /readyz, GET /livez, GET /ping, kube-probe/).

#### Scenario: Health check dropped
- **WHEN** an event contains a log with "GET /healthz HTTP/1.1 200"
- **THEN** the TriggerFilter returns DROP with rule "health_check"

### Requirement: TriggerFilter drops benign patterns
The TriggerFilter MUST drop events matching configurable benign patterns (regexes via `PIPELINE_BENIGN_PATTERNS`). Patterns are matched against event source, event type, and log bodies.

#### Scenario: Benign pattern dropped
- **WHEN** `PIPELINE_BENIGN_PATTERNS` includes "kube-system" and an event has source "kube-system/coredns"
- **THEN** the TriggerFilter returns DROP with rule "benign_pattern"

### Requirement: TriggerFilter drops events with no signal
Events with no metrics and no logs MUST be dropped — there is no signal to trigger an investigation.

#### Scenario: Empty event dropped
- **WHEN** an event has empty metrics list and empty logs list
- **THEN** the TriggerFilter returns DROP with reason "no signal"

### Requirement: TriggerFilter drops boring metrics
When all metric values are within normal thresholds and no critical keywords are present, the event MUST be dropped.

#### Scenario: All metrics normal
- **WHEN** an event has CPU at 30%, memory at 45%, and no error metrics
- **THEN** the TriggerFilter returns DROP with reason "all metrics within normal thresholds"

### Requirement: TriggerFilter fail-open default
When no rule matches an event, the TriggerFilter MUST pass the event to the LLM (fail-open). Unknown events deserve investigation.

#### Scenario: No rule matches
- **WHEN** an event does not match any TriggerFilter rule
- **THEN** the TriggerFilter returns PASS with rule "default"
