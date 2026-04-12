## ADDED Requirements

### Requirement: OTLP gRPC ingester implements the SDK Ingester Protocol
The OTLP gRPC ingester MUST implement the `octantis_plugin_sdk.Ingester` Protocol as a dedicated plugin (separate from the HTTP ingester — one transport per plugin, per the Single Responsibility Principle). Its `setup(config)` MUST create a gRPC server bound to the configured port. Its `start()` MUST bind the gRPC listener. Its `stop()` MUST gracefully stop the gRPC server. Its `events()` MUST yield SDK `Event` objects parsed from the gRPC stream.

Octantis Ingester ≠ OTel Collector receiver: the Octantis Ingester is the plugin inside the Octantis process that produces SDK `Event` instances. An external OTel Collector sending traffic to this plugin is a separate concern.

#### Scenario: gRPC ingester satisfies Ingester Protocol
- **WHEN** the Plugin Registry loads the OTLP gRPC ingester
- **THEN** `isinstance(grpc_ingester_instance, Ingester)` returns `True`

#### Scenario: Setup, start, and stop via Protocol
- **WHEN** the registry calls `setup(config)` then `start()` then `stop()`
- **THEN** the gRPC server is started and then gracefully stopped without leaving listening sockets

### Requirement: OTLP gRPC ingester registers via the octantis.ingesters entry point
The OTLP gRPC ingester MUST be declared in `pyproject.toml` under the `octantis.ingesters` entry-point group with the stable plugin name `otlp-grpc`. `main.py` MUST NOT import the ingester directly; it MUST be instantiated by the Plugin Registry.

#### Scenario: gRPC ingester discovered via entry point
- **WHEN** Octantis starts with the core package installed
- **THEN** the Plugin Registry discovers `otlp-grpc` through the `octantis.ingesters` entry-point group and `main.py` contains no direct import of the gRPC ingester module
