## ADDED Requirements

### Requirement: Registry lifecycle metrics exported
The metrics module MUST export counters and gauges for plugin lifecycle events: `octantis_plugins_discovered_total{plugin_type}`, `octantis_plugins_loaded_total{plugin_type,plugin_name}`, `octantis_plugin_setup_duration_seconds{plugin_name}`, and `octantis_plugin_teardown_duration_seconds{plugin_name}`.

#### Scenario: Plugin load recorded
- **WHEN** the Plugin Registry loads a plugin named `otlp-grpc`
- **THEN** `octantis_plugins_loaded_total{plugin_type="ingesters",plugin_name="otlp-grpc"}` increments by 1 and `octantis_plugin_setup_duration_seconds{plugin_name="otlp-grpc"}` records a non-zero duration

### Requirement: Plan gating metrics exported
The metrics module MUST export `octantis_plan_tier_info{tier}` as a gauge with value 1 for the active tier and 0 otherwise, and `octantis_plan_gating_violations_total{plugin_type,tier}` as a counter incremented when a tier limit is exceeded.

#### Scenario: Active tier reported
- **WHEN** Octantis starts with a pro-tier JWT
- **THEN** `octantis_plan_tier_info{tier="pro"}` is 1 and `octantis_plan_tier_info{tier="free"}` is 0

#### Scenario: Violation counted
- **WHEN** a free-tier deployment attempts to load two MCPConnectors and is rejected
- **THEN** `octantis_plan_gating_violations_total{plugin_type="mcp",tier="free"}` increments by 1

### Requirement: Distributed-mode metrics exported
The metrics module MUST export, when running in `ingester` or `worker` mode: `octantis_redpanda_messages_published_total` (ingester), `octantis_redpanda_messages_consumed_total` (worker), `octantis_redpanda_messages_redelivered_total{consumer_group}` (worker), and `octantis_redpanda_consumer_lag_records` (worker, as a gauge).

#### Scenario: Ingester publishes metric
- **WHEN** an event is successfully produced to the `octantis.events` topic
- **THEN** `octantis_redpanda_messages_published_total` increments by 1

#### Scenario: Worker lag observable
- **WHEN** a worker is running and has un-consumed messages in its assigned partitions
- **THEN** `octantis_redpanda_consumer_lag_records` reflects the non-zero lag

### Requirement: Standalone concurrency metrics exported
The metrics module MUST export `octantis_standalone_active_workflows` (gauge) and `octantis_standalone_semaphore_capacity` (gauge) when running in `standalone` mode.

#### Scenario: Active workflow count
- **WHEN** five workflows are running concurrently in standalone mode
- **THEN** `octantis_standalone_active_workflows` reads 5
