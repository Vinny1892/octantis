## Context

Octantis currently targets Kubernetes exclusively. The `OTelResource` model has hardcoded K8s fields, `MCPClientManager` has hardcoded `_connect_grafana()` and `_connect_k8s()` methods, the `MetricThresholdRule` assumes percentage values from pod-level metrics, and the investigator prompt references Kubernetes-specific query patterns. Node Exporter host-level metrics (from Docker hosts or AWS EC2 instances) are either dropped or misinterpreted because counter values like `node_cpu_seconds_total=123456.78` don't match the percentage-based thresholds.

The codebase is single-person, pre-production, with comprehensive test coverage. This enables aggressive refactoring without migration concerns.

Key files:
- `models/event.py`: `OTelResource` (flat K8s fields), `InvestigationResult.summary` (K8s-specific), `MCPQueryRecord.datasource` (limited to promql/logql/k8s)
- `mcp_client/manager.py`: Hardcoded Grafana + K8s connection methods
- `pipeline/trigger_filter.py`: `MetricThresholdRule` uses substring matching (`"cpu" in name`) with percentage thresholds
- `receivers/parser.py`: `_RESOURCE_ATTR_MAP` maps K8s attributes only, no counter normalization
- `config.py`: Only `GrafanaMCPSettings` and `K8sMCPSettings`
- `graph/nodes/investigator.py`: K8s-specific system prompt and `_build_trigger_context()`

## Goals / Non-Goals

**Goals:**
- Node Exporter metrics pass TriggerFilter with normalized percentage values
- Octantis auto-detects source platform (K8s, Docker, AWS) from OTLP resource attributes
- Docker MCP and AWS MCP integrate generically via registry pattern
- MCP slot model enforced: min 1 MCP total, max 1 per slot (observability + platform)
- Existing K8s flow unaffected — all tests pass
- Adding a future platform (GCP, Azure) = new `OTelResource` subclass + config entry, zero code changes in manager/detector

**Non-Goals:**
- Multiple MCPs per slot (paid tier, not designed yet)
- Mixed environment on a single instance (paid tier)
- VMware, GCP, Azure support (future PRD)
- Tier/license enforcement system
- OTel Collector or Node Exporter deployment
- Changing the LangGraph workflow structure (investigate → analyze → plan → notify stays)

## Decisions

### Decision 1: Polymorphic OTelResource via inheritance

Extract a base `OTelResource` with common fields (`service_name`, `service_namespace`, `host_name`, `extra`). Move K8s fields to `K8sResource(OTelResource)`. Add `DockerResource(OTelResource)` and `AWSResource(OTelResource)`. Each subclass implements `context_summary() -> str`.

**Why**: OCP-compliant — adding platforms = adding a subclass. Type-safe with IDE autocompletion. Polymorphic summary replaces hardcoded K8s branching in `InvestigationResult`.

**Alternatives rejected**: (a) Single flat model with all fields — grows unbounded, no type safety. (b) `extra` dict for everything — no autocompletion, string-coupled.

**Migration**: Existing code referencing `resource.k8s_namespace` etc. works via `K8sResource` subclass. `isinstance(resource, K8sResource)` for platform-specific branches. Only `InvestigationResult.summary` and `_build_trigger_context()` need updates.

### Decision 2: Parser normalizes counters, Environment Detector promotes type

Two separate responsibilities:
1. **Parser** normalizes known Node Exporter counters to percentages (e.g., `node_cpu_seconds_total` rate → CPU %) in the `MetricDataPoint.value` field
2. **Environment Detector** inspects resource attributes (or `OCTANTIS_PLATFORM`) and promotes base `OTelResource` to the correct subclass

**Why**: SRP — parser handles data shape, detector handles platform semantics. Parser shouldn't know about platforms; detector shouldn't do math.

**Normalization approach**: Parser uses a hardcoded map of known counter metric name patterns to normalization functions. Unknown counters pass through unchanged. The `MetricDataPoint` preserves the original metric name but the value becomes the normalized percentage.

### Decision 3: Registry-based MCPClientManager with MCPServerConfig

Replace hardcoded `_connect_grafana()` / `_connect_k8s()` with a registry pattern. `MCPClientManager` receives `list[MCPServerConfig]` where each config declares `name`, `slot` (observability/platform), `url`, and `headers`. The manager validates slots, connects generically via `_connect_server()`, and returns tools.

**Why**: Adding a new MCP = adding a config object, zero code change in the manager. Eliminates the pattern of adding a new `_connect_*()` method per MCP.

**Breaking change**: Constructor signature changes. Bounded impact — only `main.py` and tests instantiate `MCPClientManager`.

### Decision 4: Hardcoded slot limits (no tier system)

Slot limits hardcoded as constants: `MAX_PER_SLOT = 1`, `MIN_TOTAL = 1`. No tier/license system. When paid tier is designed, these constants become the change point.

**Why**: Simplest enforcement. No over-engineering for a feature that doesn't have a business model yet. Open-source project — limits are guidelines, not DRM.

### Decision 5: Startup retry with exponential backoff → hard fail

- **No MCP configured** → immediate startup failure (config error)
- **MCP configured but unreachable** → retry 3× with exponential backoff (2s, 4s, 8s). Hard fail if exhausted.

**Why**: Distinguishes operator error (missing config) from infrastructure timing (pod starting). Container orchestrators use readiness probes to mask the startup delay.

### Decision 6: Polymorphic context_summary() for LLM context

Each `OTelResource` subclass implements `context_summary() -> str`. `InvestigationResult.summary` and `_build_trigger_context()` call `resource.context_summary()` instead of hardcoding K8s fields.

**Why**: Adding platforms = adding a method. Base class provides generic fallback. No `isinstance()` branching needed.

## Risks / Trade-offs

- **OTelResource migration scope** → All references to `resource.k8s_*` must be audited. Mitigated by comprehensive test suite and bounded impact (only `event.py`, `investigator.py`, `analyzer.py`, `parser.py` reference these fields).
- **Counter normalization accuracy** → Single data point normalization (no rate calculation without previous point). Mitigated by treating the value as a percentage approximation and documenting the limitation. The TriggerFilter thresholds provide a safety margin.
- **No official Docker MCP server** → Mitigated by wrapping Docker SDK or using community MCP servers. Fallback: custom MCP-compatible tool server.
- **AWS MCP IAM complexity** → Mitigated by documenting minimal read-only IAM policy and starting with EC2/CloudWatch/ECS describe-only actions.
- **MCPClientManager breaking change** → Mitigated by bounded impact (only `main.py` and tests).
- **EKS dual-attribute ambiguity** → K8s detection takes priority over AWS. Mitigated by explicit `OCTANTIS_PLATFORM` override and clear documentation.
