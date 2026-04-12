## ADDED Requirements

### Requirement: SDK is distributed as a separate Apache-2.0 package
The `octantis-plugin-sdk` package MUST be published to PyPI as an independent distribution under the Apache-2.0 license. It MUST NOT import from `octantis` (the core) and MUST NOT depend on any AGPL-licensed package. Plugin authors SHALL depend on `octantis-plugin-sdk` only.

#### Scenario: SDK installed standalone
- **WHEN** a developer runs `pip install octantis-plugin-sdk` in a clean environment
- **THEN** the install succeeds without pulling in the `octantis` core package
- **AND** `import octantis_plugin_sdk` succeeds and exposes the six Protocols and shared types

#### Scenario: License declared as Apache-2.0
- **WHEN** `pip show octantis-plugin-sdk` is run
- **THEN** the License field reads `Apache-2.0`

### Requirement: SDK exposes six Protocol interfaces
The SDK MUST export, from its top-level namespace, exactly six `typing.Protocol` classes: `Ingester`, `Storage`, `MCPConnector`, `Processor`, `Notifier`, and `UIProvider`. The `Ingester` Protocol is the Octantis-side event-source contract, deliberately named distinctly from the OpenTelemetry Collector's "receiver" pipeline stage. Each Protocol MUST be decorated with `@runtime_checkable`. Each Protocol MUST define the lifecycle methods `setup(config: dict) -> None` and `teardown() -> None`, plus the role-specific methods defined in Tech Spec 005 §3.

#### Scenario: Protocol exports present
- **WHEN** a plugin author runs `from octantis_plugin_sdk import Ingester, Storage, MCPConnector, Processor, Notifier, UIProvider`
- **THEN** all six imports succeed and each is a `typing.Protocol` subclass

#### Scenario: Runtime-checkable protocol conformance
- **WHEN** a third-party class implements the `Processor` Protocol methods
- **THEN** `isinstance(instance, Processor)` returns `True`

### Requirement: SDK exposes shared dataclass types
The SDK MUST export the shared types used across Protocol boundaries — at minimum `Event`, `InvestigationResult`, `Tool`, and `PluginMetadata` — as frozen dataclasses or Pydantic models. Types MUST be importable from the top-level SDK namespace.

#### Scenario: Shared types importable
- **WHEN** a plugin author runs `from octantis_plugin_sdk import Event, InvestigationResult, Tool, PluginMetadata`
- **THEN** all four imports succeed

### Requirement: SDK surface is the stable plugin contract
The SDK MUST follow semantic versioning. A breaking change to any Protocol signature or shared type MUST produce a major-version bump of `octantis-plugin-sdk`. Minor or patch releases MUST NOT remove or rename exported symbols.

#### Scenario: Backward-compatible addition
- **WHEN** a new optional method is added to a Protocol in SDK v1.x
- **THEN** the release is published as a minor version and existing plugins continue to load without modification

#### Scenario: Breaking removal requires major bump
- **WHEN** a Protocol method is removed or its signature changes incompatibly
- **THEN** the release is published as SDK v2.0.0 and the CHANGELOG documents the break
