## 1. Data Model — OTelResource Hierarchy

- [x] 1.1 Refactor `OTelResource` in `models/event.py` to a base class with only common fields (`service_name`, `service_namespace`, `host_name`, `extra`) and a `context_summary()` method
- [x] 1.2 Create `K8sResource(OTelResource)` subclass with K8s fields (`k8s_namespace`, `k8s_pod_name`, `k8s_node_name`, `k8s_deployment_name`) and K8s-specific `context_summary()`
- [x] 1.3 Create `DockerResource(OTelResource)` subclass with Docker fields (`container_id`, `container_name`, `container_runtime`, `image_name`) and Docker-specific `context_summary()`
- [x] 1.4 Create `AWSResource(OTelResource)` subclass with AWS fields (`cloud_provider`, `cloud_region`, `instance_id`, `account_id`, `aws_service`) and AWS-specific `context_summary()`
- [x] 1.5 Update `InvestigationResult.summary` to delegate to `resource.context_summary()` instead of hardcoding K8s fields
- [x] 1.6 Extend `MCPQueryRecord.datasource` to accept `"docker"` and `"aws"` values
- [x] 1.7 Run `uv run pytest` and fix any broken tests from model changes

## 2. Config — New Settings Classes

- [x] 2.1 Add `DockerMCPSettings` with `env_prefix="DOCKER_MCP_"` (url, headers) to `config.py`
- [x] 2.2 Add `AWSMCPSettings` with `env_prefix="AWS_MCP_"` (url, headers) to `config.py`
- [x] 2.3 Add `PlatformSettings` with `env_prefix="OCTANTIS_"` (platform: Literal["k8s","docker","aws"] | None) to `config.py`
- [x] 2.4 Add `MCPRetrySettings` with `env_prefix="MCP_RETRY_"` (max_attempts=3, backoff_base=2.0) to `config.py`
- [x] 2.5 Add new settings to the `Settings` class as sub-models (docker_mcp, aws_mcp, platform, mcp_retry)
- [x] 2.6 Update `.env.example` with new environment variables

## 3. Parser — Counter Normalization

- [x] 3.1 Add Node Exporter counter normalization map in `receivers/parser.py` with known metric patterns (at minimum: `node_cpu_seconds_total`)
- [x] 3.2 Add normalization logic to `_build_metrics_event()` that normalizes known counters before creating `MetricDataPoint`
- [x] 3.3 Add `parser.counter_normalized` DEBUG log when normalization is applied
- [x] 3.4 Write unit tests for counter normalization (CPU counter → percentage, unknown metric → pass-through, gauge → unchanged)

## 4. Environment Detector

- [x] 4.1 Create `pipeline/environment_detector.py` with `EnvironmentDetector` class
- [x] 4.2 Implement K8s detection from `k8s.pod.name` or `k8s.namespace.name` in resource.extra → create `K8sResource`
- [x] 4.3 Implement Docker detection from `container.runtime=docker` or `container.id` in resource.extra → create `DockerResource`
- [x] 4.4 Implement AWS detection from `cloud.provider=aws` in resource.extra → create `AWSResource`
- [x] 4.5 Implement `OCTANTIS_PLATFORM` override that bypasses auto-detection
- [x] 4.6 Implement K8s-over-AWS priority (EKS edge case)
- [x] 4.7 Implement default-to-K8s fallback with warning log when no platform detected
- [x] 4.8 Write unit tests for all detection scenarios (K8s, Docker, AWS, EKS, override, fallback, field preservation)

## 5. TriggerFilter — Node Exporter Rules

- [x] 5.1 Update `MetricThresholdRule` to recognize `node_cpu` prefix and evaluate against `cpu_ok_below` threshold
- [x] 5.2 Update `MetricThresholdRule` to recognize `node_memory` prefix and evaluate against `memory_ok_below` threshold
- [x] 5.3 Update `MetricThresholdRule` to recognize `node_filesystem` and `node_network` prefixes
- [x] 5.4 Write unit tests for Node Exporter metric trigger scenarios (CPU above threshold, below threshold, mixed K8s+Node Exporter)

## 6. MCPClientManager — Registry Refactor

- [x] 6.1 Create `MCPServerConfig` dataclass in `mcp_client/manager.py` with `name`, `slot`, `url`, `headers` fields
- [x] 6.2 Refactor `MCPClientManager.__init__` to accept `list[MCPServerConfig]` and `MCPRetrySettings` instead of specific settings classes
- [x] 6.3 Implement `validate_slots()` that checks min 1 MCP, max 1 per slot, raises on violation
- [x] 6.4 Implement generic `connect()` that iterates configs and calls `_connect_server()` for each
- [x] 6.5 Implement startup retry with exponential backoff in `_connect_server()` using `MCPRetrySettings`
- [x] 6.6 Update `_connect_server()` to use retry settings from config
- [x] 6.7 Remove hardcoded `_connect_grafana()` and `_connect_k8s()` methods
- [x] 6.8 Write unit tests for slot validation (zero MCPs, two in same slot, valid configs)
- [x] 6.9 Write unit tests for retry logic (success on retry, exhausted retries)

## 7. Main — Wire Everything Together

- [x] 7.1 Update `main.py` to build `list[MCPServerConfig]` from settings (Grafana, K8s, Docker, AWS as applicable)
- [x] 7.2 Instantiate `MCPClientManager` with configs list and retry settings
- [x] 7.3 Wire `EnvironmentDetector` into the pipeline (after cooldown, before workflow)
- [x] 7.4 Pass `OCTANTIS_PLATFORM` from `PlatformSettings` to `EnvironmentDetector`
- [x] 7.5 Update existing tests that instantiate `MCPClientManager` to use new constructor

## 8. Investigator — Platform-Aware Prompt

- [x] 8.1 Update `INVESTIGATION_SYSTEM_PROMPT` to be platform-aware (mention Docker and AWS tools alongside K8s/PromQL/LogQL)
- [x] 8.2 Update `_build_trigger_context()` to use `resource.context_summary()` instead of hardcoding K8s fields
- [x] 8.3 Update `_classify_datasource()` to recognize Docker and AWS tool names → return `"docker"` and `"aws"` respectively
- [x] 8.4 Update `mcp_servers_used` derivation to be dynamic (from connected server names, not hardcoded list)
- [x] 8.5 Update investigator tests to cover Docker and AWS trigger contexts

## 9. Documentation Overhaul

- [x] 9.1 Rewrite `.github/OVERVIEW.md` — update architecture description and diagrams to show multi-platform (K8s, Docker, AWS) instead of K8s-only
- [x] 9.2 Update `.github/PIPELINE.md` — add Node Exporter metric examples, environment detection stage, MCP slot model
- [x] 9.3 Update `.github/ONBOARDING.md` — add Docker and AWS quickstart guides alongside existing K8s guide
- [x] 9.4 Update `.github/AGENT.md` — update investigation examples to cover Docker and AWS scenarios
- [x] 9.5 Update `.github/SECURITY.md` — add Docker MCP security (Docker socket access, read-only constraints) and AWS MCP security (IAM policy, least-privilege, credential management)
- [x] 9.6 Update `README.md` — update project description, supported platforms, and quickstart to reflect multi-platform
- [x] 9.7 Update `AGENTS.md` — reflect new models, environment detector, registry-based MCP manager, updated pipeline flow
- [x] 9.8 Audit all docs for remaining K8s-only language in generic descriptions

## 10. Integration & Final Verification

- [x] 10.1 Run `uv run pytest` — all existing tests pass with no regressions
- [x] 10.2 Verify Node Exporter metric triggers investigation end-to-end (unit test with normalized CPU event)
- [x] 10.3 Verify environment detection with Docker and AWS resource attributes (unit test)
- [x] 10.4 Verify slot validation prevents invalid MCP configurations (unit test)
- [x] 10.5 Verify `InvestigationResult.summary` outputs platform-specific context for each resource type
