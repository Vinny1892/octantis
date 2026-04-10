## ADDED Requirements

### Requirement: OTel Collector conditional subchart
The chart SHALL include the official `opentelemetry-collector` Helm chart as a conditional dependency, enabled only when `otelCollector.enabled: true`. The Collector SHALL be pre-configured to export OTLP to the Octantis Service.

#### Scenario: OTel Collector not rendered when disabled
- **WHEN** `helm template` is run with `otelCollector.enabled=false` (default)
- **THEN** no OTel Collector resources SHALL be rendered

#### Scenario: OTel Collector renders when enabled
- **WHEN** `helm template` is run with `otelCollector.enabled=true`
- **THEN** OTel Collector resources SHALL be rendered from the subchart

#### Scenario: OTLP exporter auto-wired to Octantis service
- **WHEN** `helm template` is run with `otelCollector.enabled=true`
- **THEN** the Collector config SHALL include an OTLP exporter pointing to `http://<release>-octantis:4317`

### Requirement: OTel Operator conditional subchart
The chart SHALL include the official `opentelemetry-operator` Helm chart as a conditional dependency, enabled only when `otelOperator.enabled: true`.

#### Scenario: OTel Operator not rendered when disabled
- **WHEN** `helm template` is run with `otelOperator.enabled=false` (default)
- **THEN** no OTel Operator resources SHALL be rendered

#### Scenario: OTel Operator renders when enabled
- **WHEN** `helm template` is run with `otelOperator.enabled=true`
- **THEN** OTel Operator resources SHALL be rendered from the subchart

### Requirement: OpenTelemetryCollector CR template
When both `otelOperator.enabled: true` and `otelCollector.enabled: true`, the chart SHALL create an `OpenTelemetryCollector` CR instead of relying on the Collector subchart's Deployment. The CR mode SHALL be configurable via `otelOperator.collector.mode`.

#### Scenario: CR created when both Operator and Collector enabled
- **WHEN** `helm template` is run with `otelOperator.enabled=true` and `otelCollector.enabled=true`
- **THEN** an `OpenTelemetryCollector` CR SHALL be rendered

#### Scenario: CR not created when Operator disabled
- **WHEN** `helm template` is run with `otelOperator.enabled=false` and `otelCollector.enabled=true`
- **THEN** no `OpenTelemetryCollector` CR SHALL be rendered
- **AND** the Collector subchart SHALL render its own Deployment

#### Scenario: CR mode configurable
- **WHEN** `helm template` is run with `otelOperator.enabled=true` and `otelCollector.enabled=true` and `otelOperator.collector.mode=daemonset`
- **THEN** the CR SHALL set `mode: daemonset`

#### Scenario: Operator enabled without Collector
- **WHEN** `helm template` is run with `otelOperator.enabled=true` and `otelCollector.enabled=false`
- **THEN** the OTel Operator SHALL be deployed
- **AND** no `OpenTelemetryCollector` CR SHALL be created

### Requirement: Subchart version pinning
OTel subcharts SHALL be pinned with `~` version range in Chart.yaml to allow patch updates but prevent breaking changes.

#### Scenario: Versions pinned in Chart.yaml
- **WHEN** `Chart.yaml` dependencies are read
- **THEN** each OTel subchart version SHALL use `~` prefix (e.g., `~0.x.x`)

### Requirement: Subchart values pass-through
All values under `otelCollector` (except `enabled`) and `otelOperator` (except `enabled` and `collector`) SHALL be passed through to the respective subchart.

#### Scenario: Custom Collector config passed through
- **WHEN** `helm template` is run with `otelCollector.enabled=true` and `otelCollector.config.receivers.otlp.protocols.http.endpoint="0.0.0.0:4318"`
- **THEN** the Collector config SHALL include the custom HTTP endpoint
