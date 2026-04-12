## ADDED Requirements

### Requirement: Orchestrator consumes ingesters from the Plugin Registry
The OTLP ingester orchestrator (main.py event loop) MUST obtain its ingester instances exclusively from the Plugin Registry's `octantis.ingesters` group. It MUST NOT import ingester classes directly and MUST NOT hold references to specific concrete ingester types. When multiple Ingester plugins are loaded (e.g. `otlp-grpc` and `otlp-http`), the orchestrator MUST merge their `events()` streams into a single pipeline feed.

#### Scenario: Orchestrator lists registry-loaded ingesters
- **WHEN** the orchestrator starts with the `otlp-grpc` and `otlp-http` ingesters registered via entry points
- **THEN** the orchestrator starts each ingester through the Ingester Protocol (`start()`) without importing them directly

#### Scenario: Third-party ingester included automatically
- **WHEN** a third-party package registers an additional `octantis.ingesters` plugin
- **THEN** the orchestrator discovers it via the registry alongside the built-in ingesters and merges its events into the pipeline

### Requirement: Orchestrator respects registry load order
The orchestrator MUST NOT start any ingester before the Plugin Registry has completed loading plugins in the fixed type order (Ingesters → Storage → MCP → Processors → Notifiers → UI) and the `PlanGatingEngine` has validated tier limits.

#### Scenario: Orchestrator waits for gating
- **WHEN** `PlanGatingEngine` rejects a tier violation during startup
- **THEN** the orchestrator does not start any ingester and the process exits with the gating error
