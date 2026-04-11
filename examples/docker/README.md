# Docker Host Monitoring Example

Full stack for monitoring Docker containers and host metrics with Octantis.

## Architecture

```
Docker Host
  ├── Node Exporter ──► Prometheus ──► Grafana ──► Grafana MCP ─┐
  ├── OTel Collector (hostmetrics + docker_stats) ──────────────►│ Octantis
  ├── Docker MCP (container inspect/logs/stats) ────────────────►│
  └── Containers (your workloads)                                └──► Slack/Discord
```

## Components

| Service | Image | Purpose |
|---|---|---|
| **Octantis** | `ghcr.io/vinny1892/octantis:latest` | AI monitoring agent |
| **Grafana MCP** | `ghcr.io/grafana/mcp-grafana:latest` | PromQL/LogQL queries (observability slot) |
| **Docker MCP** | `ghcr.io/docker/mcp-server-docker:latest` | Container inspection, logs, stats (platform slot) |
| **Node Exporter** | `prom/node-exporter:v1.9.1` | Host CPU, memory, disk, network metrics |
| **OTel Collector** | `otel/opentelemetry-collector-contrib:0.149.0` | Host + container metrics forwarding |
| **Grafana** | `grafana/grafana:11.6.0` | Dashboards and datasource proxy |
| **Prometheus** | `prom/prometheus:v3.4.0` | Metrics storage |
| **Loki** | `grafana/loki:3.5.0` | Log aggregation |

## Quick Start

```bash
cd examples/docker

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Start all services
docker compose up -d

# Check Octantis logs
docker compose logs octantis -f
```

## Platform Detection

The OTel Collector adds `container.runtime=docker` to resource attributes.
Octantis auto-detects this and creates a `DockerResource` with container-specific
context (container name, image, ID). The investigator prompt adapts to include
Docker-specific queries.

To force Docker detection (bypass auto-detect):

```env
OCTANTIS_PLATFORM=docker
```

## Security Notes

The Docker MCP server mounts `/var/run/docker.sock` read-only. In production,
use a Docker socket proxy (e.g., Tecnativa/docker-socket-proxy) to restrict
API access to read-only endpoints. See [SECURITY.md](../../.github/SECURITY.md#docker-mcp).
