## 1. Chart Scaffolding

- [x] 1.1 Create `charts/octantis/Chart.yaml` with apiVersion v2, name, version, appVersion, and conditional OTel subchart dependencies
- [x] 1.2 Create `charts/octantis/values.yaml` with all grouped values (octantis, grafanaMcp, k8sMcp, otelCollector, otelOperator, secrets) and three-mode secrets blocks
- [x] 1.3 Create `charts/octantis/values.schema.json` validating input types for all values
- [x] 1.4 Create `charts/octantis/templates/_helpers.tpl` with fullname, labels, selectorLabels, and name helpers
- [x] 1.5 Create `charts/octantis/templates/NOTES.txt` with post-install guidance and MCP/ESO warnings

## 2. Octantis Core Templates

- [x] 2.1 Create `charts/octantis/templates/octantis/deployment.yaml` with configurable image, resources, env from ConfigMap + Secrets, and OTLP ports
- [x] 2.2 Create `charts/octantis/templates/octantis/service.yaml` exposing ports 4317, 4318, 9090
- [x] 2.3 Create `charts/octantis/templates/octantis/configmap.yaml` mapping all octantis.* values to env vars with auto-wired MCP URLs
- [x] 2.4 Create `charts/octantis/templates/octantis/serviceaccount.yaml` with configurable name and annotations

## 3. Secrets Templates

- [x] 3.1 Create `charts/octantis/templates/octantis/secret.yaml` with conditional rendering for `create: true` mode for each sensitive value
- [x] 3.2 Add ExternalSecret CR template support: create `charts/octantis/templates/secrets/` with one ExternalSecret template per sensitive value, rendered when `externalsecret.create: true`
- [x] 3.3 Implement priority logic in Deployment env vars: `existingSecret` > `externalsecret` > `create` for each secret reference
- [x] 3.4 Add ESO reminder to NOTES.txt when any `externalsecret.create: true` is set

## 4. MCP Templates

- [x] 4.1 Create `charts/octantis/templates/grafana-mcp/deployment.yaml` with --enabled-tools, extraArgs, and Grafana credentials from values/Secrets
- [x] 4.2 Create `charts/octantis/templates/grafana-mcp/service.yaml` exposing port 8080
- [x] 4.3 Create `charts/octantis/templates/k8s-mcp/deployment.yaml` with --read-only flag and configurable args
- [x] 4.4 Create `charts/octantis/templates/k8s-mcp/service.yaml` exposing port 8080
- [x] 4.5 Create `charts/octantis/templates/k8s-mcp/serviceaccount.yaml` with configurable name
- [x] 4.6 Create `charts/octantis/templates/k8s-mcp/clusterrole.yaml` with read-only rules (get, list, watch) and additionalRules support
- [x] 4.7 Create `charts/octantis/templates/k8s-mcp/clusterrolebinding.yaml` referencing the K8s MCP ServiceAccount

## 5. OTel Subcharts

- [x] 5.1 Run `helm dependency update` to pull OTel Collector and Operator subcharts into `charts/octantis/charts/`
- [x] 5.2 Create `charts/octantis/templates/otel/opentelemetrycollector-cr.yaml` rendered only when both otelOperator and otelCollector are enabled, with configurable mode

- [x] 5.3 Add `kube-prometheus-stack` as conditional subchart dependency in `Chart.yaml`
- [x] 5.4 Pull kube-prometheus-stack subchart and commit tgz
- [x] 5.5 Add `kubePrometheusStack` values section in `values.yaml` with pass-through config
- [x] 5.6 Auto-wire Grafana MCP `grafanaUrl` when kube-prometheus-stack is enabled alongside grafanaMcp
- [x] 5.7 Configure OTel Collector Prometheus receiver when kube-prometheus-stack is enabled alongside otelCollector

## 6. Validation

- [x] 6.1 Run `helm lint charts/octantis/` and fix any warnings or errors
- [x] 6.2 Run `helm template` for all 16 toggle combinations and verify all render without errors
- [x] 6.7 Run `helm template` for all 32 toggle combinations (2^5 with kubePrometheusStack) and verify all render
- [x] 6.8 Verify kube-prometheus-stack + grafanaMcp auto-wires Grafana URL
- [x] 6.9 Verify kube-prometheus-stack + otelCollector configures Prometheus receiver
- [x] 6.3 Verify auto-wiring: enable grafanaMcp → GRAFANA_MCP_URL appears in ConfigMap
- [x] 6.4 Verify auto-wiring: enable k8sMcp → K8S_MCP_URL appears in ConfigMap
- [x] 6.5 Verify secrets priority: existingSecret > externalsecret > create
- [x] 6.6 Verify ExternalSecret CR renders only when `externalsecret.create: true`

## 7. CI Pipeline

- [x] 7.1 Add `helm` job to `.github/workflows/ci.yml` with lint and template matrix
- [x] 7.3 Update CI template matrix to cover 32 combinations (2^5 with kubePrometheusStack)
- [x] 7.2 Create `.github/workflows/helm-publish.yml` triggered on `chart-v*` tag: lint → template matrix → package → OCI push → git-cliff changelog → GitHub Release

## 8. ArtifactHub & Publishing

- [x] 8.1 Create `artifacthub-repo.yml` at repo root with owner metadata
- [x] 8.2 Add ArtifactHub annotations to Chart.yaml (license, changes)

## 9. Documentation

- [x] 9.1 Create `charts/octantis/README.md` with configuration table, quickstart, architecture Mermaid diagram, and examples
- [x] 9.2 Create `charts/octantis/examples/values-minimal.yaml` (Octantis only)
- [x] 9.3 Create `charts/octantis/examples/values-full-stack.yaml` (everything enabled)
- [x] 9.4 Create `charts/octantis/examples/values-external-mcp.yaml` (Octantis + external MCP URLs)
- [x] 9.5 Update `.github/ONBOARDING.md` with Helm install as recommended K8s deployment method
- [x] 9.6 Update `.github/OVERVIEW.md` to reference the Helm chart in the deployment section
- [x] 9.8 Update `charts/octantis/README.md` with kube-prometheus-stack configuration section
- [x] 9.9 Update example values to include kube-prometheus-stack options
- [x] 9.10 Update `.github/ONBOARDING.md` to mention kube-prometheus-stack integration
- [x] 9.11 Update `.github/OVERVIEW.md` architecture to include kube-prometheus-stack
