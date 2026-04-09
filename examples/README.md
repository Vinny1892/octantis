# Examples

Deployment and configuration examples for Octantis.

## Table of Contents

- [Deployment Options](#deployment-options)
  - [Docker Compose (Local Development)](#docker-compose-local-development)
  - [Kubernetes (Production)](#kubernetes-production)
  - [Key Environment Variables](#key-environment-variables)
- [OTel Collector Configuration](#otel-collector-configuration)
  - [Versions](#versions)
  - [collector-config.yaml](#collector-configyaml)
  - [otel-operator/](#otel-operator)
  - [Pipeline Overview](#pipeline-overview)

## Deployment Options

### Docker Compose (Local Development)

Full stack for local development: Octantis + Grafana MCP + Grafana + Prometheus + Loki + OTel Collector.

**Prerequisites:**
- Docker and Docker Compose
- `ANTHROPIC_API_KEY` set in environment or `.env` file

```bash
cd examples/docker-compose
cp ../../.env.example .env
# Edit .env and set ANTHROPIC_API_KEY

docker compose up -d
```

| Service          | Port | Description              |
|------------------|------|--------------------------|
| Grafana          | 3000 | Grafana UI (admin/admin) |
| Octantis OTLP    | 4317 | gRPC receiver            |
| Octantis OTLP    | 4318 | HTTP receiver            |
| Prometheus       | 9090 | Prometheus UI            |
| Octantis Metrics | 9091 | Prometheus metrics       |
| Loki             | 3100 | Log aggregation          |

**Included services:** Octantis (built from source), mcp-grafana (auto-provisioned token), OTel Collector (host metrics + OTLP forwarding), Grafana (pre-configured datasources), Prometheus, Loki.

### Kubernetes (Production)

Production-ready manifests for deploying Octantis in a Kubernetes cluster.

**Prerequisites:**
- Kubernetes cluster with `monitoring` namespace
- Grafana with Prometheus + Loki datasources configured

```bash
kubectl create namespace monitoring

kubectl create secret generic octantis-secrets \
  --namespace monitoring \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --from-literal=GRAFANA_MCP_API_KEY=glsa_...

cd examples/kubernetes
kubectl apply -f mcp-grafana.yaml   # Required: Grafana MCP server
kubectl apply -f octantis.yaml      # Required: Octantis
kubectl apply -f mcp-k8s.yaml       # Optional: K8s MCP server (recommended)
```

| Manifest          | Description                                              |
|-------------------|----------------------------------------------------------|
| `octantis.yaml`   | Deployment + Service + ConfigMap for Octantis             |
| `mcp-grafana.yaml`| Deployment + Service for Grafana MCP server               |
| `mcp-k8s.yaml`    | Deployment + Service + ServiceAccount + RBAC for K8s MCP  |

**Enabling K8s MCP:** Deploy `mcp-k8s.yaml`, uncomment `K8S_MCP_URL` in the `octantis-config` ConfigMap, then `kubectl rollout restart deployment/octantis -n monitoring`.

### Key Environment Variables

| Variable                         | Default              | Description                          |
|----------------------------------|----------------------|--------------------------------------|
| `LLM_MODEL`                     | `claude-sonnet-4-6` | Model for analysis and planning      |
| `LLM_INVESTIGATION_MODEL`       | (same as LLM_MODEL)  | Model for MCP investigation          |
| `GRAFANA_MCP_URL`               | —                    | Grafana MCP SSE endpoint             |
| `K8S_MCP_URL`                   | —                    | K8s MCP SSE endpoint (optional)      |
| `INVESTIGATION_MAX_QUERIES`     | `10`                 | Max MCP queries per investigation    |
| `INVESTIGATION_TIMEOUT_SECONDS` | `60`                 | Total investigation timeout          |
| `PIPELINE_CPU_THRESHOLD`        | `75.0`               | CPU % trigger threshold              |
| `PIPELINE_MEMORY_THRESHOLD`     | `80.0`               | Memory % trigger threshold           |
| `PIPELINE_COOLDOWN_SECONDS`     | `300`                | Cooldown between duplicate events    |
| `MIN_SEVERITY_TO_NOTIFY`        | `MODERATE`           | Minimum severity for notifications   |

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

# Or with the binary
otelcol-contrib --config=examples/collector-config.yaml
```

### `otel-operator/`

Kubernetes manifests for deploying the collector via the OpenTelemetry Operator.

1. **Install the operator** (one-time):

   ```bash
   helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
   helm repo update
   helm install otel-operator open-telemetry/opentelemetry-operator \
     --namespace otel-system --create-namespace \
     --set manager.image.tag=0.107.0
   ```

2. **Deploy the collector CR**:

   ```bash
   kubectl apply -f examples/otel-operator/namespace.yaml
   kubectl apply -f examples/otel-operator/opentelemetrycollector.yaml
   ```

### Pipeline Overview

```
Kubernetes nodes/pods
        |
        v
  OTel Collector
  (kubeletstats receiver + k8sattributes processor)
        |
        v
  Octantis (gRPC :4317 / HTTP :4318)
        |
        v
  MCP Investigation (Grafana MCP + K8s MCP)
        |
        v
  Analysis → Planning → Notification
```
