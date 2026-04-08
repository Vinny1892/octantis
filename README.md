# Octantis

Intelligent infrastructure monitoring agent. Receives metrics and logs via OTLP, uses an LLM to autonomously investigate and classify incidents, and notifies Slack/Discord with a concrete remediation plan.

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

## Quickstart — Kind Dev Cluster

The fastest way to try Octantis is with the included Kind dev environment, which sets up a full observability stack:

```bash
# Prerequisites: Docker, Kind, kubectl, Helm

# 1. Configure secrets
export OPENROUTER_API_KEY="sk-or-..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# 2. Create the cluster (Kind + Prometheus + Grafana + Mimir + OTel + MetalLB + MCPs + Octantis)
bash dev/setup.sh
```

See [`dev/README.md`](dev/README.md) for full details (architecture, secrets, troubleshooting).

## Deploy to a Kubernetes Cluster

Example manifests for deploying Octantis + MCP servers to an existing cluster:

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

## Development

```bash
# Install dependencies
uv sync

# Run tests (98 tests, all mocked — no real LLM/MCP calls)
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## Documentation

- [Architecture Overview](docs/overview.md) — data flow and design decisions
- [Filter Pipeline](docs/pipeline.md) — event ingestion and pre-filtering
- [LangGraph Agent](docs/agent.md) — investigation, analysis, planning, and notification
- [Onboarding](docs/onboarding.md) — setup guide and code map
