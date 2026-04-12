## ADDED Requirements

### Requirement: Trigger filter implements the SDK Processor Protocol
The trigger filter MUST implement the `octantis_plugin_sdk.Processor` Protocol. Its `process(event)` MUST return either the event (pass) or `None` (drop). Its `setup(config)` MUST load trigger rules; its `teardown()` MUST release any held resources.

#### Scenario: Trigger filter satisfies Processor Protocol
- **WHEN** the Plugin Registry loads the trigger filter
- **THEN** `isinstance(trigger_filter, Processor)` returns `True`

### Requirement: Trigger filter registers via the octantis.processors entry point with priority 100
The trigger filter MUST be declared in `pyproject.toml` under the `octantis.processors` entry-point group with plugin name `trigger-filter` and a default `priority = 100`. Operators MUST be able to override the priority via configuration.

#### Scenario: Trigger filter runs first among built-in processors
- **WHEN** built-in processors (`trigger-filter` at 100 and `fingerprint-cooldown` at 200) are loaded
- **THEN** `trigger-filter.process(event)` is invoked before `fingerprint-cooldown.process(event)` for every event

#### Scenario: Operator overrides priority
- **WHEN** configuration sets `trigger-filter.priority = 50`
- **THEN** the registry orders `trigger-filter` before any processor with priority ≥ 50
