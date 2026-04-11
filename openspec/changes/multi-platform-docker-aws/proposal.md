## Why

Octantis only works with Kubernetes. The TriggerFilter drops Node Exporter host-level metrics (Docker hosts, AWS EC2/ECS), `OTelResource` only has K8s fields, `MCPClientManager` is hardcoded for Grafana + K8s MCPs, and the investigation prompt assumes Kubernetes. Teams running Docker or AWS cannot use Octantis even if they already have Node Exporter + OTel Collector sending OTLP data. Expanding to Docker and AWS unlocks the majority of smaller and mid-size teams while establishing a plug-in pattern for future platforms (VMware, GCP, Azure).

## What Changes

- **OTelResource hierarchy**: Extract base class with common fields, add `K8sResource`, `DockerResource`, `AWSResource` subclasses with polymorphic `context_summary()`
- **Environment Detector**: New component that promotes base `OTelResource` to typed subclass based on OTLP resource attributes or `OCTANTIS_PLATFORM` env var
- **Parser counter normalization**: Normalize Node Exporter counters (`node_cpu_seconds_total`, `node_memory_MemAvailable_bytes`, etc.) to percentages for threshold evaluation
- **TriggerFilter Node Exporter rules**: `MetricThresholdRule` extended to recognize `node_cpu`, `node_memory`, `node_filesystem`, `node_network` metric name prefixes with host-level thresholds
- **MCPClientManager registry refactor**: Replace hardcoded `_connect_grafana()` / `_connect_k8s()` with generic registry pattern using `MCPServerConfig` dataclass. Slot validation: min 1 MCP, max 1 observability + 1 platform
- **Docker MCP support**: Configurable via `DOCKER_MCP_URL`, wired into the registry as a platform-slot MCP
- **AWS MCP support**: Configurable via `AWS_MCP_URL`, wired into the registry as a platform-slot MCP
- **Config expansion**: New `DockerMCPSettings`, `AWSMCPSettings`, `PlatformSettings`, `MCPRetrySettings` in config.py
- **Investigation prompt update**: Investigator system prompt becomes platform-aware, trigger context builder uses `resource.context_summary()`
- **InvestigationResult.summary**: Delegates to `resource.context_summary()` instead of hardcoding K8s fields
- **Startup retry with backoff**: MCP connections retry with exponential backoff (3 attempts, 2s base) before hard failure
- **MCP query datasource extension**: `MCPQueryRecord.datasource` gains `"docker"` and `"aws"` values

## Capabilities

### New Capabilities
- `environment-detector`: Detects source platform (K8s, Docker, AWS) from OTLP resource attributes or explicit config, promotes OTelResource to typed subclass
- `docker-mcp`: Docker MCP client integration for container inspection, logs, and resource stats
- `aws-mcp`: AWS MCP client integration for EC2 inspection, CloudWatch metrics, and ECS task status

### Modified Capabilities
- `otlp-parser`: Adds counter normalization for Node Exporter metrics (counters to percentages)
- `trigger-filter`: Adds Node Exporter metric name recognition and host-level thresholds to MetricThresholdRule
- `mcp-client`: Refactored from hardcoded methods to registry pattern with slot validation (observability + platform), startup retry with backoff

## Impact

- **Models** (`models/event.py`): `OTelResource` becomes abstract base; new `K8sResource`, `DockerResource`, `AWSResource` subclasses; `InvestigationResult.summary` delegates to `resource.context_summary()`
- **Config** (`config.py`): New settings classes for Docker MCP, AWS MCP, platform override, MCP retry
- **Parser** (`receivers/parser.py`): Counter normalization logic for known Node Exporter metrics
- **Pipeline** (`pipeline/trigger_filter.py`): `MetricThresholdRule` extended with host-level metric matching
- **MCP Client** (`mcp_client/manager.py`): Full refactor to registry pattern — **BREAKING** constructor change
- **Investigator** (`graph/nodes/investigator.py`): Platform-aware prompt and trigger context builder
- **Main** (`main.py`): Updated MCPClientManager instantiation with registry config, environment detector wiring
- **Tests**: All existing tests must pass; new tests for environment detection, slot validation, counter normalization, Node Exporter trigger rules
- **Dependencies**: No new external dependencies (MCP SSE client and langchain-mcp-adapters already present)
