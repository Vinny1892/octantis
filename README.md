# Octantis

Intelligent infrastructure monitoring agent for EKS/Kubernetes.

Consumes OTel metrics/logs from Redpanda, uses an LLM to assess true operational
severity, and notifies Slack + Discord with a concrete remediation plan.

## Architecture

```
OTel Collector → Redpanda → Octantis Agent → Slack / Discord
                                 ↕
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

# 3. Run
uv run octantis
```

## Development

```bash
# Run tests
uv run pytest

# Run with local Redpanda (docker-compose)
docker compose up -d redpanda
uv run octantis
```

## Configuration

All settings are via environment variables (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `REDPANDA_BROKERS` | `localhost:9092` | Comma-separated broker list |
| `REDPANDA_TOPIC` | `otel-infra-events` | Topic to consume |
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
