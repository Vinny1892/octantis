## ADDED Requirements

### Requirement: Parser emits the shared SDK Event type
The OTLP parser MUST produce outputs whose type is, or is structurally compatible with, `octantis_plugin_sdk.Event`. The SDK `Event` type becomes the canonical event shape consumed by Processor, MCPConnector, and Notifier plugins. Any internal alias MUST preserve the fields exposed by the SDK type.

#### Scenario: Parser output type-compatible with SDK Event
- **WHEN** the parser converts an OTLP payload into an event
- **THEN** the returned object satisfies the `octantis_plugin_sdk.Event` structural contract (all required fields present with the declared types)

### Requirement: Parser is importable without importing core runtime
The parser module MUST be importable by plugin authors who depend only on `octantis-plugin-sdk` shapes. The parser MUST NOT pull in runtime components (registry, gating, distributed runner) at import time.

#### Scenario: No runtime import at parser load
- **WHEN** a test imports the parser module in isolation
- **THEN** no registry, gating, or runtime side effects are triggered
