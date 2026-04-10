## ADDED Requirements

### Requirement: Grafana MCP conditional deployment
The chart SHALL render Grafana MCP Deployment and Service templates only when `grafanaMcp.enabled: true`. The Deployment SHALL use image `ghcr.io/vinny1892/mcp-grafana` with configurable tag and `--enabled-tools` flag.

#### Scenario: Grafana MCP not rendered when disabled
- **WHEN** `helm template` is run with `grafanaMcp.enabled=false` (default)
- **THEN** no Grafana MCP resources SHALL be rendered

#### Scenario: Grafana MCP renders when enabled
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true`
- **THEN** a Deployment and Service for Grafana MCP SHALL be rendered

#### Scenario: Enabled tools flag applied
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true` and `grafanaMcp.enabledTools="prometheus,loki"`
- **THEN** the Grafana MCP container args SHALL include `--enabled-tools=prometheus,loki`

#### Scenario: Extra args applied
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true` and `grafanaMcp.extraArgs` contains `--disable-oncall`
- **THEN** the Grafana MCP container args SHALL include `--disable-oncall`

### Requirement: Grafana MCP auto-wires URL to Octantis
When `grafanaMcp.enabled: true`, the Octantis ConfigMap SHALL include `GRAFANA_MCP_URL` pointing to the in-chart Grafana MCP Service. In-chart URL takes precedence over `octantis.externalMcp.grafanaUrl`.

#### Scenario: Auto-wired URL in ConfigMap
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true`
- **THEN** the Octantis ConfigMap SHALL contain `GRAFANA_MCP_URL: "http://<release>-grafana-mcp:8080/sse"`

#### Scenario: In-chart takes precedence over external URL
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true` and `octantis.externalMcp.grafanaUrl="http://other:8080/sse"`
- **THEN** the ConfigMap SHALL use the auto-wired in-chart URL
- **AND** SHALL NOT use `http://other:8080/sse`

### Requirement: Grafana MCP credentials from Secrets
Grafana MCP Deployment SHALL reference the Grafana URL and API key from values or Secrets, not hardcode them.

#### Scenario: Grafana URL from values
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true` and `grafanaMcp.grafanaUrl="http://grafana.monitoring:3000"`
- **THEN** the Grafana MCP container env SHALL include the Grafana URL

### Requirement: K8s MCP conditional deployment
The chart SHALL render K8s MCP Deployment, Service, ServiceAccount, ClusterRole, and ClusterRoleBinding templates only when `k8sMcp.enabled: true`.

#### Scenario: K8s MCP not rendered when disabled
- **WHEN** `helm template` is run with `k8sMcp.enabled=false` (default)
- **THEN** no K8s MCP resources SHALL be rendered

#### Scenario: K8s MCP renders when enabled
- **WHEN** `helm template` is run with `k8sMcp.enabled=true`
- **THEN** Deployment, Service, ServiceAccount, ClusterRole, and ClusterRoleBinding for K8s MCP SHALL be rendered

### Requirement: K8s MCP read-only RBAC
The K8s MCP ClusterRole SHALL grant read-only permissions (get, list, watch) on core, apps, batch, networking, and autoscaling API groups. Additional rules SHALL be configurable via `k8sMcp.rbac.additionalRules`.

#### Scenario: Default read-only ClusterRole
- **WHEN** `helm template` is run with `k8sMcp.enabled=true`
- **THEN** the ClusterRole SHALL grant get, list, watch on pods, deployments, services, events, and other standard resources

#### Scenario: Additional RBAC rules appended
- **WHEN** `helm template` is run with `k8sMcp.enabled=true` and `k8sMcp.rbac.additionalRules` contains a rule for `secrets`
- **THEN** the ClusterRole SHALL include both the default read-only rules and the additional secrets rule

### Requirement: K8s MCP auto-wires URL to Octantis
When `k8sMcp.enabled: true`, the Octantis ConfigMap SHALL include `K8S_MCP_URL` pointing to the in-chart K8s MCP Service. In-chart URL takes precedence over `octantis.externalMcp.k8sUrl`.

#### Scenario: Auto-wired K8s MCP URL in ConfigMap
- **WHEN** `helm template` is run with `k8sMcp.enabled=true`
- **THEN** the Octantis ConfigMap SHALL contain `K8S_MCP_URL: "http://<release>-k8s-mcp:8080/sse"`

### Requirement: K8s MCP read-only flag
The K8s MCP container SHALL include the `--read-only` flag by default to prevent write operations against the Kubernetes API.

#### Scenario: Read-only flag in container args
- **WHEN** `helm template` is run with `k8sMcp.enabled=true`
- **THEN** the K8s MCP container args SHALL include `--read-only`

### Requirement: MCP resource limits configurable
Both Grafana MCP and K8s MCP SHALL have configurable resource requests and limits via values.

#### Scenario: Custom resource limits applied
- **WHEN** `helm template` is run with `grafanaMcp.enabled=true` and `grafanaMcp.resources.limits.memory=512Mi`
- **THEN** the Grafana MCP Deployment SHALL have `resources.limits.memory: 512Mi`
