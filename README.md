# Octantis

[![CI](https://github.com/Vinny1892/octantis/actions/workflows/ci.yml/badge.svg)](https://github.com/Vinny1892/octantis/actions/workflows/ci.yml)
[![Build mcp-grafana](https://github.com/Vinny1892/octantis/actions/workflows/mcp-grafana.yml/badge.svg)](https://github.com/Vinny1892/octantis/actions/workflows/mcp-grafana.yml)
[![GHCR](https://img.shields.io/badge/ghcr.io-octantis-blue?logo=github)](https://github.com/Vinny1892/octantis/pkgs/container/octantis)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Intelligent infrastructure monitoring agent. Receives metrics and logs via OTLP, uses an LLM to autonomously investigate and classify incidents, and notifies Slack/Discord with a concrete remediation plan.

## List of Contents

- [How it works](#how-it-works)
- [Container Image](#container-image)
- [Running Octantis](#running-octantis)
  - [Local Kind Cluster (quickstart)](#local-kind-cluster-quickstart)
  - [Existing Kubernetes Cluster](#existing-kubernetes-cluster)
  - [From Source](#from-source)
- [Configuration](#configuration)
- [MCP Servers](#mcp-servers)
- [Severity Levels](#severity-levels)
- [Contributing](#contributing)
- [Documentation](#documentation)

## How it works

```
OTel Collector ──OTLP──► Octantis ──MCP──► Grafana / Kubernetes API
                              │
                              ├── LLM (Anthropic / OpenRouter / Bedrock)
                              │
                              └──► Slack / Discord (remediation plan)
```

1. **Receive** — OTLP metrics/logs from OpenTelemetry Collector (gRPC :4317, HTTP :4318)
2. **Filter** — Drop health checks, benign patterns, and deduplicate via fingerprint cooldown
3. **Investigate** — LLM autonomously queries Prometheus (PromQL), Loki (LogQL), and optionally Kubernetes via MCP
4. **Analyze** — Classify severity (CRITICAL / MODERATE / LOW / NOT_A_PROBLEM) with confidence score
5. **Plan** — Generate actionable remediation steps with real `kubectl` commands
6. **Notify** — Send to Slack and/or Discord (only if severity >= threshold)

## Container Image

```
ghcr.io/vinny1892/octantis:latest
```

Published automatically by CI on every push to `master`. Pin to a specific commit SHA for production (e.g., `ghcr.io/vinny1892/octantis:dba131d`).

## Running Octantis

### Local Kind Cluster (quickstart)

The fastest way to try Octantis. The `dev/` directory contains scripts that create a Kind cluster with a full observability stack (Prometheus, Grafana, Mimir, OTel Collector, MetalLB, MCP servers, and Octantis itself) — everything needed to run end-to-end locally.

```bash
# Prerequisites: Docker, Kind, kubectl, Helm

# 1. Configure secrets
export OPENROUTER_API_KEY="sk-or-..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# 2. Create the cluster
bash dev/setup.sh
```

See [`dev/README.md`](dev/README.md) for full details (architecture, secrets, troubleshooting).

### Existing Kubernetes Cluster

For deploying Octantis to a real cluster (EKS, GKE, AKS, etc.), use the example manifests:

```bash
# 1. Create secrets
kubectl create secret generic octantis-secrets \
  --namespace monitoring \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --from-literal=GRAFANA_MCP_API_KEY=glsa_...

# 2. Deploy MCP servers + Octantis
kubectl apply -f examples/kubernetes/
```

See [`examples/kubernetes/`](examples/kubernetes/) for the manifests. Customize the image, model, and notification settings in the ConfigMap.

Image: `ghcr.io/vinny1892/octantis:latest`

### From Source

To run Octantis outside a cluster (requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)):

```bash
uv sync
cp .env.example .env   # edit with your keys
uv run octantis
```

See [Onboarding — Local Development](.github/onboarding.md#local-development) for full setup details.

## Configuration

All settings via environment variables. See [`.env.example`](.env.example) for the full list.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openrouter`, or `bedrock` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model ID (e.g., `anthropic/claude-sonnet-4-6` for OpenRouter, `global.anthropic.claude-opus-4-6-v1` for Bedrock) |
| `GRAFANA_MCP_URL` | — | Grafana MCP SSE endpoint (required) |
| `K8S_MCP_URL` | — | Kubernetes MCP SSE endpoint (recommended) |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Minimum severity to send alerts |
| `LANGUAGE` | `en` | Output language (`en`, `pt-br`) |
| `SLACK_WEBHOOK_URL` | — | Slack notifications (empty = disabled) |
| `DISCORD_WEBHOOK_URL` | — | Discord notifications (empty = disabled) |

## MCP Servers

Octantis connects to MCP servers via SSE for real-time cluster observability:

| Server | Image | Purpose |
|---|---|---|
| Grafana MCP | `ghcr.io/vinny1892/mcp-grafana:latest` | PromQL, LogQL, dashboard queries |
| Kubernetes MCP | `ghcr.io/containers/kubernetes-mcp-server:latest` | Pod status, events, deployments, logs |

## Severity Levels

| Level | Meaning | Action |
|---|---|---|
| `CRITICAL` | Service down / data loss risk | Notify + Action Plan |
| `MODERATE` | Degraded / trending bad | Notify + Action Plan |
| `LOW` | Minor anomaly | Log only |
| `NOT_A_PROBLEM` | Expected / false positive | Log only |

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md).

## Documentation

- [Architecture Overview](.github/overview.md) — data flow and design decisions
- [Filter Pipeline](.github/pipeline.md) — event ingestion and pre-filtering
- [LangGraph Agent](.github/agent.md) — investigation, analysis, planning, and notification
- [Onboarding](.github/onboarding.md) — setup guide and code map
