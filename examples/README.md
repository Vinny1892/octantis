# Examples

Deployment and configuration examples for Octantis across all supported platforms.

## List of Contents

- [Platform Examples](#platform-examples)
  - [Kubernetes](#kubernetes)
  - [Docker](#docker)
  - [AWS](#aws)
- [Local Development (Docker Compose)](#local-development-docker-compose)
- [OTel Collector Configuration](#otel-collector-configuration)
  - [Versions](#versions)
  - [collector-config.yaml](#collector-configyaml)
  - [otel-operator/](#otel-operator)
- [Key Environment Variables](#key-environment-variables)

## Platform Examples

Octantis supports three platform environments. Each uses a **slot model**: one observability MCP (Grafana) + one platform MCP (K8s, Docker, or AWS).

| Platform | Example dir | Platform MCP | Detection |
|---|---|---|---|
| **Kubernetes** | [`kubernetes/`](kubernetes/) | K8s MCP | `k8s.pod.name` or `k8s.namespace.name` in OTLP attributes |
| **Docker** | [`docker/`](docker/) | Docker MCP | `container.runtime=docker` or `container.id` in OTLP attributes |
| **AWS** | [`aws/`](aws/) | AWS MCP | `cloud.provider=aws` in OTLP attributes |

### Kubernetes

Production manifests for deploying Octantis in a Kubernetes cluster.

```bash
kubectl create namespace monitoring

kubectl create secret generic octantis-secrets \
  --namespace monitoring \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --from-literal=GRAFANA_MCP_API_KEY=glsa_...

cd examples/kubernetes
kubectl apply -f mcp-grafana.yaml   # Required: Grafana MCP (observability slot)
kubectl apply -f octantis.yaml      # Required: Octantis
kubectl apply -f mcp-k8s.yaml       # Optional: K8s MCP (platform slot)
```

| Manifest | Description |
|---|---|
| `octantis.yaml` | Deployment + Service + ConfigMap |
| `mcp-grafana.yaml` | Grafana MCP server (observability slot) |
| `mcp-k8s.yaml` | K8s MCP server + ServiceAccount + RBAC (platform slot) |

See [`kubernetes/`](kubernetes/) for details.

### Docker

Full stack for monitoring Docker containers and host metrics.

```bash
cd examples/docker
export ANTHROPIC_API_KEY="sk-ant-..."
docker compose up -d
```

Includes: Octantis, Grafana MCP, **Docker MCP**, Node Exporter, OTel Collector (with docker_stats receiver), Grafana, Prometheus, Loki.

| Service | Port |
|---|---|
| Grafana | 3000 |
| Octantis OTLP (gRPC) | 4317 |
| Octantis OTLP (HTTP) | 4318 |
| Prometheus | 9090 |
| Octantis Metrics | 9091 |

See [`docker/README.md`](docker/README.md) for details.

### AWS

AWS deployment via ECS Fargate or local simulation.

```bash
# Local simulation
cd examples/aws
export ANTHROPIC_API_KEY="sk-ant-..."
docker compose up -d

# ECS production — see aws/README.md for full instructions
aws ecs register-task-definition --cli-input-json file://aws/ecs-task-definition.json
```

Includes: ECS task definition (Octantis + Grafana MCP + AWS MCP sidecars), IAM policy (read-only), OTel Collector config with AWS resource detection.

See [`aws/README.md`](aws/README.md) for ECS deployment, IAM setup, and Bedrock configuration.

---

## Local Development (Docker Compose)

The [`docker-compose/`](docker-compose/) directory contains a local development stack that builds Octantis from source. This is the quickest way to iterate on code changes:

```bash
cd examples/docker-compose
cp ../../.env.example .env
# Edit .env with your ANTHROPIC_API_KEY

docker compose up -d
```

This stack does **not** include a platform MCP — it's meant for K8s-style dev only (matching the Kind dev cluster). For Docker or AWS platform development, use the respective platform example instead.

---

## OTel Collector Configuration

### Versions

| Component | Version | Image |
|---|---|---|
| OTel Collector (contrib) | **0.149.0** | `otel/opentelemetry-collector-contrib:0.149.0` |
| OTel Operator | **0.107.0** | Installed via Helm chart `open-telemetry/opentelemetry-operator` |

> Tested on 2026-04-06. Check [collector releases](https://github.com/open-telemetry/opentelemetry-collector-releases/releases) and [operator releases](https://github.com/open-telemetry/opentelemetry-operator/releases) for newer versions.

### `collector-config.yaml`

Standalone OTel Collector configuration file. Use this when running the collector as a binary or Docker container outside of Kubernetes.

```bash
# Run with Docker
docker run --rm \
  -v $(pwd)/examples/collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  -p 4317:4317 -p 4318:4318 \
  otel/opentelemetry-collector-contrib:0.149.0
```

### `otel-operator/`

Kubernetes manifests for deploying the collector via the OpenTelemetry Operator.

```bash
# Install the operator (one-time)
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm install otel-operator open-telemetry/opentelemetry-operator \
  --namespace otel-system --create-namespace

# Deploy the collector CR
kubectl apply -f examples/otel-operator/
```

### Platform-specific OTel Collector configs

Each platform example includes its own OTel Collector config with the appropriate resource attributes:

| Platform | Config | Key resource attributes |
|---|---|---|
| Docker | [`docker/otel-collector-config.yaml`](docker/otel-collector-config.yaml) | `container.runtime=docker` |
| AWS | [`aws/otel-collector-config.yaml`](aws/otel-collector-config.yaml) | `cloud.provider=aws`, `cloud.region`, `host.id` |
| K8s | Use `otel-operator/` or `collector-config.yaml` with k8sattributes processor | `k8s.pod.name`, `k8s.namespace.name` |

---

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openrouter`, or `bedrock` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model for analysis and planning |
| `GRAFANA_MCP_URL` | -- | Grafana MCP SSE endpoint (observability slot) |
| `K8S_MCP_URL` | -- | K8s MCP SSE endpoint (platform slot) |
| `DOCKER_MCP_URL` | -- | Docker MCP SSE endpoint (platform slot) |
| `AWS_MCP_URL` | -- | AWS MCP SSE endpoint (platform slot) |
| `OCTANTIS_PLATFORM` | (auto) | Force platform: `k8s`, `docker`, or `aws` |
| `INVESTIGATION_MAX_QUERIES` | `10` | Max MCP queries per investigation |
| `INVESTIGATION_TIMEOUT_SECONDS` | `60` | Total investigation timeout |
| `PIPELINE_CPU_THRESHOLD` | `75.0` | CPU % trigger threshold |
| `PIPELINE_MEMORY_THRESHOLD` | `80.0` | Memory % trigger threshold |
| `PIPELINE_COOLDOWN_SECONDS` | `300` | Cooldown between duplicate events |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Minimum severity for notifications |
