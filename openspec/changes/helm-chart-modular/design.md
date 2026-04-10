## Context

Octantis has example Kubernetes manifests in `examples/kubernetes/` — static YAML files hardcoded to the `monitoring` namespace. There is no Helm chart, no OCI artifact, no ArtifactHub listing, and no CI for chart publishing. Operators must manually deploy and wire 3-7 components (Octantis, OTel Collector, Grafana MCP, K8s MCP, Secrets). The Octantis Docker image is already published at `ghcr.io/vinny1892/octantis:latest`.

Secret management is a critical concern: operators use different strategies ranging from plain Kubernetes Secrets (dev) to External Secrets Operator with vault backends (production). The chart must support both patterns without forcing a choice.

## Goals / Non-Goals

**Goals:**
- Single `helm install` deploys any combination of Octantis + OTel + MCPs
- Values API grouped by feature domain, matching `config.py` structure
- Dual secrets: native Kubernetes Secret creation (`create: true`) and External Secrets Operator (`externalsecret` references)
- All 16 toggle combinations render without errors via `helm template`
- Chart published as OCI artifact to ghcr.io on tag push
- Chart discoverable on ArtifactHub

**Non-Goals:**
- Helm chart testing framework (ct, helm-unittest) — deferred to future iteration
- Docker Compose deployment
- Ingress / Gateway API resources
- Monitoring stack (Prometheus, Loki, Grafana) deployment
- Docker MCP / AWS MCP templates (deferred to PRD 003 implementation)

## Decisions

### Decision 1: Values grouped by feature domain

Group values by component: `octantis.*`, `grafanaMcp.*`, `k8sMcp.*`, `otelCollector.*`, `otelOperator.*`, `secrets.*`. Mirrors `config.py` structure.

**Alternatives:**
- Flat top-level keys: rejected — doesn't scale with 50+ keys
- Config-mirrored env vars: rejected — not idiomatic Helm, poor DX

**Trade-off**: `--set` flags are verbose (e.g., `--set octantis.llm.provider=openrouter`). Acceptable since operators use `-f values.yaml` files.

### Decision 2: Chart lives in same repository

`charts/octantis/` in the Octantis repo. CI publishes when a `chart-v*` tag is pushed.

**Trade-off**: Chart releases share git history with the app. Mitigated by independent versioning and `chart-v*` tag prefix.

### Decision 3: Auto-wiring MCP URLs via template logic

When `grafanaMcp.enabled: true`, the ConfigMap template computes `GRAFANA_MCP_URL` as `http://{{ release }}-grafana-mcp:8080/sse`. Priority: in-chart component > external URL > not set.

**Trade-off**: Operator cannot override the auto-wired URL when the component is enabled. Must disable in-chart component and use `externalMcp` for custom URLs.

### Decision 4: Three-mode secrets support

Each sensitive value supports three modes:

| Mode | Config | Use Case |
|------|--------|----------|
| Chart-managed Secret | `create: true` + `value` | Dev/test convenience |
| Existing Secret reference | `existingSecret: "name"` | External Secrets Operator, Sealed Secrets, manual |
| ExternalSecret CR | `externalsecret.create: true` + `externalsecret.spec` | External Secrets Operator managed by the chart |

**Priority**: `existingSecret` > `externalsecret.create` > `create`. When `existingSecret` is set, chart does not create any Secret or ExternalSecret CR — the operator manages the Secret externally.

**Alternatives:**
- Only `create` + `existingSecret` (no ESO): rejected — forces operators to manually create ExternalSecret CRs outside the chart
- Only ExternalSecret (no native Secrets): rejected — adds ESO as a hard dependency

**Trade-off**: Three modes adds complexity to the secret templates. Mitigated by clear priority rules and `values.schema.json` validation.

### Decision 5: Conditional subchart dependencies

OTel Collector and Operator use `condition:` in Chart.yaml. When disabled, nothing is rendered — no CRDs, no RBAC, no pods.

### Decision 6: Tag-based publishing with git-cliff

Pushing `chart-v*` tag triggers: lint → template matrix → package → OCI push → git-cliff changelog → GitHub Release.

**Trade-off**: Manual tag creation. Acceptable — git-cliff can automate this.

## Risks / Trade-offs

- **OTel subchart major version breaks compatibility** → Pin versions with `~` in Chart.yaml. Test upgrades before bumping.
- **MCP server images change CLI flags** → Pin image tags in values.yaml defaults. Document supported versions.
- **Three-mode secrets complexity** → `values.schema.json` validates input. Clear priority rules prevent ambiguous states.
- **Combinatorial explosion of toggle states** → Automate `helm template` for all 16 combinations in CI. Focus manual testing on 4-5 common setups.
- **External Secrets Operator not installed** → `externalsecret` values are opt-in. Chart works without ESO installed. NOTES.txt warns if ESO is enabled but CRDs are missing.
- **Users confuse chart version with app version** → Clear docs. `appVersion` in Chart.yaml always matches default image tag.
