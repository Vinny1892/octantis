# Examples

Configuration examples for integrating OpenTelemetry Collector with Octantis.

## Versions

| Component | Version | Image |
|---|---|---|
| OTel Collector (contrib) | **0.149.0** | `otel/opentelemetry-collector-contrib:0.149.0` |
| OTel Operator | **0.107.0** | Installed via Helm chart `open-telemetry/opentelemetry-operator` |

> Tested on 2026-04-06. Check [collector releases](https://github.com/open-telemetry/opentelemetry-collector-releases/releases) and [operator releases](https://github.com/open-telemetry/opentelemetry-operator/releases) for newer versions.

## Contents

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

The `OpenTelemetryCollector` CR creates a collector Deployment in the `monitoring` namespace that scrapes Kubernetes metrics (kubeletstats) and forwards them to Octantis via OTLP/gRPC.

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
```
