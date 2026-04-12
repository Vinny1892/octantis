## ADDED Requirements

### Requirement: Registry discovers plugins via Python entry points
The Plugin Registry MUST discover plugins by querying the six fixed entry-point groups: `octantis.ingesters`, `octantis.storage`, `octantis.mcp`, `octantis.processors`, `octantis.notifiers`, and `octantis.ui`. The group names MUST be treated as a frozen public contract and MUST NOT change once released. Discovery MUST use `importlib.metadata.entry_points()` and MUST NOT scan the filesystem.

#### Scenario: Third-party plugin discovered via entry point
- **WHEN** a package registers an entry point under `octantis.notifiers` and is installed in the active environment
- **THEN** the registry discovers the plugin at startup without any change to `main.py` or configuration files

#### Scenario: Unknown entry-point group ignored
- **WHEN** a package registers an entry point under `octantis.unknown_group`
- **THEN** the registry does not load it and does not error

### Requirement: Registry loads plugins in fixed order by type
The registry MUST load plugins in the fixed order: Ingesters → Storage → MCP → Processors → Notifiers → UI. Within the Processor type, plugins MUST be ordered by an integer `priority` attribute ascending (lower priority runs first). Built-in defaults: `TriggerFilter` priority=100, `FingerprintCooldown` priority=200.

#### Scenario: Ingester initialized before MCP
- **WHEN** both an Ingester and an MCPConnector plugin are installed
- **THEN** the Ingester plugin's `setup()` completes before the MCPConnector's `setup()` begins

#### Scenario: Processor ordering by priority
- **WHEN** processors with priorities 100, 200, and 150 are installed
- **THEN** they are invoked in the order 100 → 150 → 200

### Requirement: Registry detects duplicate plugin names
The registry MUST reject two plugins registering the same `name` within the same entry-point group. On conflict, the registry MUST fail startup with a clear error identifying both packages.

#### Scenario: Duplicate notifier name
- **WHEN** two installed packages register a notifier named `slack`
- **THEN** startup fails with an error naming both packages and the conflicting plugin name

### Requirement: Registry logs every lifecycle event
The registry MUST emit structured logs at `INFO` level for each of: plugin discovered, plugin loaded, `setup()` started, `setup()` completed, `teardown()` started, `teardown()` completed. Each log MUST include `plugin_name`, `plugin_type`, `plugin_version`, and `source_package`.

#### Scenario: Lifecycle log for a loaded plugin
- **WHEN** the registry loads a plugin named `otlp-grpc` version `0.1.0`
- **THEN** a log record with fields `plugin_name=otlp-grpc`, `plugin_type=ingesters`, `plugin_version=0.1.0`, and event `plugin.setup_completed` is emitted

### Requirement: Registry teardown runs in reverse load order
On shutdown, the registry MUST invoke `teardown()` on every loaded plugin in the reverse of the load order (UI → Notifiers → Processors → MCP → Storage → Ingesters). A `teardown()` exception MUST be logged but MUST NOT prevent teardown of remaining plugins.

#### Scenario: Teardown continues after a plugin raises
- **WHEN** one Notifier's `teardown()` raises an exception during shutdown
- **THEN** the registry logs the error and still invokes `teardown()` on all other plugins
