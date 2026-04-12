## ADDED Requirements

### Requirement: Fingerprint cooldown implements the SDK Processor Protocol
The fingerprint cooldown MUST implement the `octantis_plugin_sdk.Processor` Protocol. Its `process(event)` MUST return the event when the fingerprint is outside the cooldown window and `None` when it is within. Its `setup(config)` MUST initialize the cooldown store; its `teardown()` MUST flush any in-memory state.

#### Scenario: Fingerprint cooldown satisfies Processor Protocol
- **WHEN** the Plugin Registry loads the fingerprint cooldown
- **THEN** `isinstance(fingerprint_cooldown, Processor)` returns `True`

### Requirement: Fingerprint cooldown registers via the octantis.processors entry point with priority 200
The fingerprint cooldown MUST be declared in `pyproject.toml` under the `octantis.processors` entry-point group with plugin name `fingerprint-cooldown` and a default `priority = 200`. Operators MUST be able to override the priority via configuration.

#### Scenario: Cooldown runs after trigger filter by default
- **WHEN** the built-in `trigger-filter` (priority 100) and `fingerprint-cooldown` (priority 200) are both loaded
- **THEN** the registry invokes them in the order trigger-filter → fingerprint-cooldown for every event

#### Scenario: Operator overrides priority
- **WHEN** configuration sets `fingerprint-cooldown.priority = 50`
- **THEN** the registry orders `fingerprint-cooldown` before any processor with priority ≥ 50
