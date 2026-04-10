## ADDED Requirements

### Requirement: kube-prometheus-stack conditional subchart
The chart SHALL include the official `kube-prometheus-stack` Helm chart as a conditional dependency, enabled only when `kubePrometheusStack.enabled: true`. The subchart installs Prometheus Operator, Prometheus, Alertmanager, Grafana, kube-state-metrics, and node-exporter.

#### Scenario: kube-prometheus-stack not rendered when disabled
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=false` (default)
- **THEN** no kube-prometheus-stack resources SHALL be rendered

#### Scenario: kube-prometheus-stack renders when enabled
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=true`
- **THEN** Prometheus Operator, Prometheus, Grafana, and related resources SHALL be rendered from the subchart

### Requirement: OTel Collector integration with kube-prometheus-stack
When both `kubePrometheusStack.enabled: true` and `otelCollector.enabled: true`, the OTel Collector SHALL be configured with a Prometheus receiver that scrapes metrics from the kube-prometheus-stack Prometheus instance. The Collector then exports these metrics to Octantis via OTLP.

#### Scenario: OTel Collector scrapes from kube-prometheus-stack
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=true` and `otelCollector.enabled=true`
- **THEN** the OTel Collector config SHALL include a Prometheus receiver scraping the in-chart Prometheus instance

#### Scenario: OTel Collector without kube-prometheus-stack works independently
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=false` and `otelCollector.enabled=true`
- **THEN** the OTel Collector config SHALL NOT reference the kube-prometheus-stack Prometheus

### Requirement: Grafana MCP auto-wiring with kube-prometheus-stack Grafana
When both `kubePrometheusStack.enabled: true` and `grafanaMcp.enabled: true`, the Grafana MCP `grafanaUrl` SHALL default to the in-chart Grafana service.

#### Scenario: Grafana MCP uses in-chart Grafana URL
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=true` and `grafanaMcp.enabled=true`
- **THEN** the Grafana MCP env SHALL include `GRAFANA_URL` pointing to the in-chart Grafana service (e.g., `http://<release>-grafana:3000`)

#### Scenario: Custom Grafana URL takes precedence
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=true` and `grafanaMcp.enabled=true` and `grafanaMcp.grafanaUrl="http://custom-grafana:3000"`
- **THEN** the Grafana MCP env SHALL use the custom URL

### Requirement: kube-prometheus-stack values pass-through
All values under `kubePrometheusStack` (except `enabled`) SHALL be passed through to the subchart.

#### Scenario: Custom Grafana admin password passed through
- **WHEN** `helm template` is run with `kubePrometheusStack.enabled=true` and `kubePrometheusStack.grafana.adminPassword="mypass"`
- **THEN** the Grafana instance SHALL use the provided admin password

### Requirement: Subchart version pinning
The kube-prometheus-stack subchart SHALL be pinned with a specific version range in Chart.yaml.

#### Scenario: Version pinned in Chart.yaml
- **WHEN** `Chart.yaml` dependencies are read
- **THEN** the kube-prometheus-stack entry SHALL have a pinned version
