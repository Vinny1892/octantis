# Octantis

Intelligent infrastructure monitoring agent for EKS/Kubernetes.

Receives OTel metrics/logs directly via OTLP (gRPC + HTTP), uses an LLM to assess
true operational severity, and notifies Slack + Discord with a concrete remediation plan.

## Architecture

```
OTel Collector ──OTLP/gRPC:4317──► Octantis Agent → Slack / Discord
OTel Collector ──OTLP/HTTP:4318──►       ↕
                          Prometheus API / Kubernetes API / Grafana MCP
                                         ↕
                                  LLM (Anthropic / OpenRouter)
```

## Quickstart

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Run (starts OTLP receivers on ports 4317/4318)
uv run octantis
```

## Development

```bash
# Run tests
uv run pytest

# Run locally — configure OTel Collector to export to localhost:4317
uv run octantis
```

## Configuration

All settings are via environment variables (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `OTLP_GRPC_PORT` | `4317` | gRPC receiver port |
| `OTLP_HTTP_PORT` | `4318` | HTTP receiver port |
| `OTLP_GRPC_ENABLED` | `true` | Enable/disable gRPC transport |
| `OTLP_HTTP_ENABLED` | `true` | Enable/disable HTTP transport |
| `OTLP_QUEUE_MAX_SIZE` | `1000` | Max events buffered before drop |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openrouter` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model name |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus base URL |
| `K8S_IN_CLUSTER` | `false` | Use in-cluster K8s config |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Min severity to send alerts |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL |
| `DISCORD_WEBHOOK_URL` | — | Discord webhook URL |

## Severity Levels

| Level | Meaning | Action |
|---|---|---|
| `CRITICAL` | Service down / data loss risk | Notify + Action Plan |
| `MODERATE` | Degraded / trending bad | Notify + Action Plan |
| `LOW` | Minor anomaly | Log only (configurable) |
| `NOT_A_PROBLEM` | Expected / false positive | Log only |

## Docker

```bash
docker build -t octantis .
docker run --env-file .env octantis
```

## Documentation

- [Overview](docs/overview.md) — architecture and design decisions
- [Pipeline](docs/pipeline.md) — event ingestion and pre-filtering
- [Agent](docs/agent.md) — LangGraph workflow (collect → analyze → plan → notify)
- [Onboarding](docs/onboarding.md) — getting started guide
