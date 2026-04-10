## ADDED Requirements

### Requirement: Chart scaffolding with Chart.yaml and values.yaml
The chart SHALL live at `charts/octantis/` with a `Chart.yaml` declaring `apiVersion: v2`, independent semver `version`, and `appVersion` tracking the Octantis image tag. The `values.yaml` SHALL group all settings by feature domain (`octantis.*`, `grafanaMcp.*`, `k8sMcp.*`, `otelCollector.*`, `otelOperator.*`, `secrets.*`).

#### Scenario: Chart.yaml declares correct metadata
- **WHEN** `charts/octantis/Chart.yaml` is read
- **THEN** it SHALL contain `apiVersion: v2`, a semver `version`, `appVersion` matching the default Octantis image tag, and `name: octantis`

#### Scenario: values.yaml groups by feature domain
- **WHEN** `charts/octantis/values.yaml` is read
- **THEN** keys SHALL be grouped under `octantis`, `grafanaMcp`, `k8sMcp`, `otelCollector`, `otelOperator`, and `secrets` top-level sections

### Requirement: Octantis Deployment template
The chart SHALL render an Octantis Deployment with configurable image, replica count, resources, environment variables from ConfigMap and Secrets, and OTLP ports (4317 gRPC, 4318 HTTP, 9090 metrics).

#### Scenario: Minimal deployment renders
- **WHEN** `helm template` is run with default values
- **THEN** a Deployment SHALL be rendered with image `ghcr.io/vinny1892/octantis`, 1 replica, and ports 4317, 4318, 9090 exposed

#### Scenario: Resources are configurable
- **WHEN** `helm template` is run with `octantis.resources.limits.cpu=1`
- **THEN** the Deployment SHALL have `resources.limits.cpu: "1"`

### Requirement: Octantis Service template
The chart SHALL render a Service exposing OTLP ports (4317, 4318) and metrics port (9090).

#### Scenario: Service exposes all ports
- **WHEN** `helm template` is run with default values
- **THEN** a Service SHALL be rendered with ports 4317, 4318, and 9090

### Requirement: Octantis ConfigMap template
The chart SHALL render a ConfigMap mapping all `octantis.*` values to environment variables matching `config.py` settings. MCP URLs SHALL be auto-wired when in-chart MCPs are enabled.

#### Scenario: ConfigMap includes OTLP settings
- **WHEN** `helm template` is run with `octantis.otlp.grpc.port=4317`
- **THEN** the ConfigMap SHALL contain `OTLP_GRPC_PORT: "4317"`

#### Scenario: ConfigMap auto-wires Grafana MCP URL
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true`
- **THEN** the ConfigMap SHALL contain `GRAFANA_MCP_URL` pointing to `http://<release>-grafana-mcp:8080/sse`

### Requirement: Octantis ServiceAccount template
The chart SHALL render a ServiceAccount for Octantis with configurable name and annotations.

#### Scenario: ServiceAccount created by default
- **WHEN** `helm template` is run with default values
- **THEN** a ServiceAccount SHALL be rendered with name `<release>-octantis`

### Requirement: Values schema validation
The chart SHALL include `values.schema.json` that validates all input types (booleans, strings, integers, objects).

#### Scenario: Invalid toggle value rejected
- **WHEN** `helm template` is run with `otelCollector.enabled="yes"` (string instead of boolean)
- **THEN** the command SHALL fail with a validation error

### Requirement: Helpers template
The chart SHALL include `_helpers.tpl` with standard Helm helpers: `octantis.fullname`, `octantis.labels`, `octantis.selectorLabels`, and `octantis.name`.

#### Scenario: Fullname helper produces correct name
- **WHEN** release name is `my-octantis`
- **THEN** `octantis.fullname` SHALL produce `my-octantis`

### Requirement: NOTES.txt post-install guidance
The chart SHALL render a NOTES.txt with pod status instructions, warnings for missing configuration, and documentation links.

#### Scenario: Warning when no MCP configured
- **WHEN** `helm install` is run with all MCPs disabled and no external MCP URLs
- **THEN** NOTES.txt SHALL include a warning that no MCP server is configured
