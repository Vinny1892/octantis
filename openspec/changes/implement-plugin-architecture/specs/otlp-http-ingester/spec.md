## ADDED Requirements

### Requirement: OTLP HTTP ingester implements the SDK Ingester Protocol
The OTLP HTTP ingester MUST implement the `octantis_plugin_sdk.Ingester` Protocol as a dedicated plugin (separate from the gRPC ingester — one transport per plugin, per the Single Responsibility Principle). Its `setup(config)` MUST create an HTTP server bound to the configured port. Its `start()` MUST bind the HTTP listener. Its `stop()` MUST gracefully stop the HTTP server. Its `events()` MUST yield SDK `Event` objects parsed from HTTP request bodies.

Octantis Ingester ≠ OTel Collector receiver: the Octantis Ingester is the plugin inside the Octantis process that produces SDK `Event` instances. An external OTel Collector sending traffic to this plugin is a separate concern.

#### Scenario: HTTP ingester satisfies Ingester Protocol
- **WHEN** the Plugin Registry loads the OTLP HTTP ingester
- **THEN** `isinstance(http_ingester_instance, Ingester)` returns `True`

#### Scenario: HTTP ingester can be loaded independently of the gRPC ingester
- **WHEN** only the HTTP ingester is enabled in configuration
- **THEN** the ingester starts and accepts HTTP OTLP traffic, and the gRPC ingester is not loaded

### Requirement: OTLP HTTP ingester registers via the octantis.ingesters entry point
The OTLP HTTP ingester MUST be declared in `pyproject.toml` under the `octantis.ingesters` entry-point group with the stable plugin name `otlp-http`. `main.py` MUST NOT import the ingester directly.

#### Scenario: HTTP ingester discovered via entry point
- **WHEN** Octantis starts with the core package installed
- **THEN** the Plugin Registry discovers `otlp-http` through the `octantis.ingesters` entry-point group
