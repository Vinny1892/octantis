## Why

Octantis has no standardized Kubernetes deployment method. Operators must manually create Deployments, Services, ConfigMaps, Secrets, and wire up MCP servers and OTel Collectors across 3-7 YAML files with hardcoded values. A single `helm install` should deploy any combination of the stack in under 2 minutes. Secret management must support both native Kubernetes Secrets and External Secrets Operator for production-grade credential management.

## What Changes

- New modular Helm chart at `charts/octantis/` with toggleable components (OTel Collector, OTel Operator, Grafana MCP, K8s MCP, kube-prometheus-stack)
- Octantis core templates: Deployment, Service, ConfigMap, ServiceAccount
- Grafana MCP and K8s MCP as in-chart templates with auto-wired URLs
- OTel Collector and OTel Operator as conditional subchart dependencies
- kube-prometheus-stack as conditional subchart dependency, integrated with OTel Collector for metrics collection
- Three-mode secrets support: native Kubernetes Secrets (`create: true`), External Secrets Operator (`externalsecret` references), and existing Secret references
- `values.schema.json` for input validation
- NOTES.txt with post-install guidance
- CI pipeline: `helm lint` + 32-combination `helm template` matrix in existing `ci.yml`
- Release pipeline: `chart-v*` tag triggers OCI push to ghcr.io + GitHub Release via git-cliff
- ArtifactHub metadata (`artifacthub-repo.yml`)
- Chart documentation: README, example values files, updates to ONBOARDING.md and OVERVIEW.md
- OpenTelemetryCollector CR template when both Operator and Collector are enabled

## Capabilities

### New Capabilities
- `helm-chart-core`: Octantis core deployment templates (Deployment, Service, ConfigMap, ServiceAccount, Secret) and chart scaffolding (Chart.yaml, values.yaml, values.schema.json, _helpers.tpl, NOTES.txt)
- `helm-secrets`: Dual-mode secrets management supporting native Kubernetes Secret creation, existing Secret references, and External Secrets Operator (ExternalSecret CR) for each sensitive value (Anthropic API key, OpenRouter API key, Grafana MCP API key, Slack webhook URL, Discord webhook URL)
- `helm-otel-subcharts`: Conditional OTel Collector and OTel Operator subchart dependencies with auto-wired OTLP exporter config and OpenTelemetryCollector CR template
- `helm-mcp-templates`: Grafana MCP and K8s MCP in-chart deployment templates with auto-wired MCP URLs, RBAC (K8s MCP), and security hardening
- `helm-ci-publish`: CI validation (lint + template matrix), release workflow (OCI push + git-cliff + GitHub Release), and ArtifactHub configuration
- `helm-kube-prometheus-stack`: kube-prometheus-stack as conditional subchart dependency with OTel Collector integration for metrics collection
- `helm-documentation`: Chart README, example values files, and updates to repository documentation (ONBOARDING.md, OVERVIEW.md)

### Modified Capabilities


## Impact

- **New directory**: `charts/octantis/` with full chart structure (templates, charts/, examples/)
- **CI changes**: New `helm` job in `.github/workflows/ci.yml`; new `.github/workflows/helm-publish.yml`
- **New file**: `artifacthub-repo.yml` at repo root
- **Docs updated**: `.github/ONBOARDING.md`, `.github/OVERVIEW.md`
- **Dependencies**: `opentelemetry-collector`, `opentelemetry-operator`, and `kube-prometheus-stack` Helm charts as subchart dependencies
- **External images**: `ghcr.io/vinny1892/octantis`, `ghcr.io/vinny1892/mcp-grafana`, `ghcr.io/containers/kubernetes-mcp-server`
- **No breaking changes**: Greenfield chart, existing manifests in `examples/kubernetes/` remain as reference
