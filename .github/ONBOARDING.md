---
title: "Onboarding — Zero to Running"
description: "How to set up Octantis and contribute to the codebase"
---

# Onboarding — Zero to Running

## List of Contents

- [Prerequisites](#prerequisites)
- [Container Image](#container-image)
- [Setup — Kind Dev Cluster (recommended)](#setup--kind-dev-cluster-recommended)
- [Deploy to an Existing Kubernetes Cluster](#deploy-to-an-existing-kubernetes-cluster)
  - [Bedrock Example](#bedrock-example)
- [Local Development](#local-development)
- [Sending a Test Event](#sending-a-test-event)
- [Running Tests](#running-tests)
  - [Lint and Formatting](#lint-and-formatting)
- [Code Reading Map](#code-reading-map)
- [Environment Variables — Full Reference](#environment-variables--full-reference)

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/)
- For local development: Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)

## Container Image

```
ghcr.io/vinny1892/octantis:latest
```

Published automatically by CI on every push to `master`. For production, pin to a specific commit SHA (e.g., `ghcr.io/vinny1892/octantis:dba131d`).

## Setup — Kind Dev Cluster (recommended)

Octantis receives metrics and logs via OTLP. The fastest way to try it is with the included Kind dev environment, which spins up a cluster with a full observability stack:

- Prometheus + Grafana + Alertmanager (kube-prometheus-stack)
- Mimir (long-term TSDB)
- OpenTelemetry Collector
- MetalLB (LoadBalancer)
- Grafana MCP (`ghcr.io/vinny1892/mcp-grafana:latest`)
- Kubernetes MCP (`ghcr.io/containers/kubernetes-mcp-server:latest`)
- Octantis (`ghcr.io/vinny1892/octantis:latest`)

```bash
# 1. Configure secrets (choose one option)

# Option A: environment variables
export OPENROUTER_API_KEY="sk-or-..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Option B: 1Password CLI (once per machine)
bash dev/op-setup.sh

# 2. Create the cluster (~5 min)
bash dev/setup.sh

# To recreate from scratch
bash dev/setup.sh --force
```

| Service | URL | Credentials |
|---|---|---|
| Grafana | http://grafana.octantis.cluster.local | admin / admin |
| Mimir API | http://mimir.octantis.cluster.local | — |
| nginx-demo | http://demo.octantis.cluster.local | — |

The `setup.sh` script configures local DNS automatically (MetalLB IP → `/etc/hosts`).

See [`dev/README.md`](../dev/README.md) for full details (architecture, troubleshooting, secrets).

## Deploy to an Existing Kubernetes Cluster

### Helm Chart (recommended)

```bash
# Add the chart repository
helm registry login ghcr.io

# Install Octantis only (minimal)
helm install octantis oci://ghcr.io/vinny1892/charts/octantis \
  -n monitoring --create-namespace \
  --set secrets.anthropicApiKey.create=true \
  --set secrets.anthropicApiKey.value="sk-ant-..."

# Install with Grafana MCP and K8s MCP
helm install octantis oci://ghcr.io/vinny1892/charts/octantis \
  -n monitoring --create-namespace \
  -f charts/octantis/examples/values-full-stack.yaml

# Install full stack including monitoring (kube-prometheus-stack)
helm install octantis oci://ghcr.io/vinny1892/charts/octantis \
  -n monitoring --create-namespace \
  --set grafanaMcp.enabled=true \
  --set k8sMcp.enabled=true \
  --set otelCollector.enabled=true \
  --set kubePrometheusStack.enabled=true \
  --set kubePrometheusStack.grafana.adminPassword=admin
```

See [`charts/octantis/README.md`](../charts/octantis/README.md) for the full configuration reference, secrets management (native K8s Secrets, External Secrets Operator, existing Secrets), and example values files.

### Example Manifests (alternative)

For quick testing without Helm, use the static manifests:

```bash
# 1. Create namespace and secrets
kubectl create namespace monitoring
kubectl create secret generic octantis-secrets \
  --namespace monitoring \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --from-literal=GRAFANA_MCP_API_KEY=glsa_...

# 2. Deploy MCP servers + Octantis
kubectl apply -f examples/kubernetes/
```

The manifests in [`examples/kubernetes/`](../examples/kubernetes/) include:

| Manifest | Description | Image |
|---|---|---|
| `octantis.yaml` | Deployment + Service + ConfigMap | `ghcr.io/vinny1892/octantis:latest` |
| `mcp-grafana.yaml` | Grafana MCP Server | `ghcr.io/vinny1892/mcp-grafana:latest` |
| `mcp-k8s.yaml` | Kubernetes MCP Server (read-only) | `ghcr.io/containers/kubernetes-mcp-server:latest` |

Customize the ConfigMap in `octantis.yaml` to adjust provider, model, notifications, etc.

### Bedrock Example

```yaml
# In octantis.yaml ConfigMap
LLM_PROVIDER: "bedrock"
LLM_MODEL: "global.anthropic.claude-opus-4-6-v1"
# AWS_REGION_NAME via env var or IAM role (IRSA on EKS)
```

## Local Development

To run Octantis outside the cluster (code development):

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env with your keys
```

Minimal configuration:

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Grafana MCP (requires a running mcp-grafana — can be in the Kind cluster)
GRAFANA_MCP_URL=http://localhost:8080/sse
GRAFANA_MCP_API_KEY=glsa_...

LOG_LEVEL=DEBUG

# Disable notifications during dev
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
```

```bash
uv run octantis
```

Expected output:

```
{"version":"0.2.0","event":"octantis.starting"}
{"server":"grafana","tool_count":34,"event":"mcp.connected"}
{"grpc_port":4317,"http_port":4318,"event":"octantis.ready"}
```

**Note:** Octantis depends on MCP servers for investigation. Without Grafana MCP, it operates in degraded mode (analyzes only with trigger data). Without Kubernetes MCP, it loses pod/events context but works normally.

## Sending a Test Event

Use `curl` to send an OTLP/HTTP event directly to Octantis:

```bash
# High-CPU event — should trigger MCP investigation
curl -X POST http://localhost:4318/v1/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "resourceMetrics": [{
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "api-server"}},
          {"key": "k8s.namespace.name", "value": {"stringValue": "production"}},
          {"key": "k8s.pod.name", "value": {"stringValue": "api-server-abc123"}},
          {"key": "k8s.deployment.name", "value": {"stringValue": "api-server"}}
        ]
      },
      "scopeMetrics": [{
        "metrics": [{
          "name": "cpu_usage",
          "unit": "%",
          "gauge": {
            "dataPoints": [{"asDouble": 95.0}]
          }
        }]
      }]
    }]
  }'
```

In the Kind cluster, real events already flow automatically — the OTel Collector scrapes kube-state-metrics every 30s and forwards to Octantis.

## Running Tests

```bash
uv run pytest                          # all tests (98)
uv run pytest tests/test_trigger_filter.py -v  # trigger filter only
uv run pytest tests/test_investigator.py -v    # investigator only
uv run pytest -k "cooldown" -v         # by name
```

All tests use mocks — no real calls to the LLM, MCP, or external APIs.

### Lint and Formatting

```bash
uv run ruff check src/ tests/         # lint
uv run ruff format src/ tests/        # auto-format
```

---

## Code Reading Map

Depending on what you want to understand or modify:

### "I want to adjust what reaches the LLM"
-> `src/octantis/pipeline/trigger_filter.py` — add/modify rules
-> `src/octantis/pipeline/cooldown.py:21` — adjust the fingerprint
-> `.env` — `PIPELINE_*` to tune without changing code

### "I want to change how the LLM investigates events"
-> `src/octantis/graph/nodes/investigator.py:28` — `INVESTIGATION_SYSTEM_PROMPT`
-> `src/octantis/mcp_client/manager.py` — MCP connection and tool discovery
-> `.env` — `INVESTIGATION_*` to adjust budget and timeouts

### "I want to change how the LLM classifies events"
-> `src/octantis/graph/nodes/analyzer.py:14` — `SYSTEM_PROMPT`
-> `src/octantis/models/analysis.py` — add fields to `SeverityAnalysis`

### "I want to change the generated action plan"
-> `src/octantis/graph/nodes/planner.py:14` — `SYSTEM_PROMPT`
-> `src/octantis/models/action_plan.py` — add `StepType` or fields

### "I want to add a notification channel"
-> Create `src/octantis/notifiers/pagerduty.py` implementing `.send(investigation, analysis, action_plan)`
-> Instantiate and call in `src/octantis/graph/nodes/notifier.py`
-> Add settings in `src/octantis/config.py`

### "I want to add internal metrics"
-> `src/octantis/metrics.py` — define new Counters/Histograms
-> Instrument in the relevant nodes

### "I want to understand the OTLP format"
-> `src/octantis/receivers/parser.py` — OTLP Protobuf/JSON -> InfraEvent
-> The `resourceMetrics` and `resourceLogs` fields follow the OTLP/JSON schema

---

## Environment Variables — Full Reference

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG / INFO / WARNING / ERROR` |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Minimum severity to trigger Slack/Discord |
| `LANGUAGE` | `en` | LLM output language (`en`, `pt-br`) |
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openrouter`, or `bedrock` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model ID for analyzer and planner |
| `LLM_INVESTIGATION_MODEL` | (= LLM_MODEL) | Model ID for investigator (optional) |
| `ANTHROPIC_API_KEY` | — | Anthropic key (required if provider=anthropic) |
| `OPENROUTER_API_KEY` | — | OpenRouter key (required if provider=openrouter) |
| `AWS_REGION_NAME` | — | AWS region (required if provider=bedrock). Credentials via standard AWS chain |
| `GRAFANA_MCP_URL` | — | Grafana MCP SSE URL (required) |
| `GRAFANA_MCP_API_KEY` | — | Grafana service account API key |
| `K8S_MCP_URL` | — | K8s MCP SSE URL (recommended). Image: `ghcr.io/containers/kubernetes-mcp-server:latest` |
| `INVESTIGATION_MAX_QUERIES` | `10` | Max MCP queries per investigation |
| `INVESTIGATION_TIMEOUT_SECONDS` | `60` | Total investigation timeout |
| `INVESTIGATION_QUERY_TIMEOUT_SECONDS` | `10` | Per-query MCP timeout |
| `OTLP_GRPC_PORT` | `4317` | gRPC receiver port |
| `OTLP_HTTP_PORT` | `4318` | HTTP receiver port |
| `OTLP_GRPC_ENABLED` | `true` | Enable gRPC receiver |
| `OTLP_HTTP_ENABLED` | `true` | Enable HTTP receiver |
| `OTLP_QUEUE_MAX_SIZE` | `1000` | Max event queue size |
| `METRICS_PORT` | `9090` | Prometheus metrics port |
| `METRICS_ENABLED` | `true` | Enable metrics endpoint |
| `SLACK_WEBHOOK_URL` | — | Incoming webhook URL (empty = disabled) |
| `SLACK_BOT_TOKEN` | — | Bot token (alternative to webhook) |
| `SLACK_CHANNEL` | `#infra-alerts` | Channel (only used with bot token) |
| `DISCORD_WEBHOOK_URL` | — | Webhook URL (empty = disabled) |
| `PIPELINE_CPU_THRESHOLD` | `75.0` | CPU % to consider anomalous |
| `PIPELINE_MEMORY_THRESHOLD` | `80.0` | Memory % to consider anomalous |
| `PIPELINE_ERROR_RATE_THRESHOLD` | `0.01` | Error req/s to consider anomalous |
| `PIPELINE_BENIGN_PATTERNS` | `""` | Comma-separated regexes to always drop |
| `PIPELINE_COOLDOWN_SECONDS` | `300` | Suppression seconds per fingerprint |
| `PIPELINE_COOLDOWN_MAX_ENTRIES` | `1000` | Max fingerprints in memory |
