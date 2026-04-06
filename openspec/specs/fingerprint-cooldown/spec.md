## ADDED Requirements

### Requirement: FingerprintCooldown suppresses repeated triggers
The `FingerprintCooldown` SHALL compute a fingerprint from namespace + workload + event type + metric names and suppress events matching a fingerprint seen within the cooldown window. The cooldown period MUST be configurable via `PIPELINE_COOLDOWN_SECONDS` (default 300s).

#### Scenario: First occurrence passes
- **WHEN** an event with a new fingerprint arrives
- **THEN** the cooldown returns `True` (should investigate) and records the fingerprint

#### Scenario: Repeated event within cooldown suppressed
- **WHEN** an event with a known fingerprint arrives within 300s of the last occurrence
- **THEN** the cooldown returns `False` (suppress), logs `cooldown.suppressed` with remaining cooldown time

#### Scenario: Cooldown expired re-triggers
- **WHEN** an event with a known fingerprint arrives after 300s since last occurrence
- **THEN** the cooldown returns `True` (should investigate) with fresh MCP data

### Requirement: Sliding window cooldown
The cooldown window MUST be sliding — each occurrence resets the timer. This prevents a persistent issue from being re-investigated while it's still firing.

#### Scenario: Sliding window resets
- **WHEN** event A fires at t=0, again at t=200s, and again at t=400s
- **THEN** the event at t=200s resets the window, so t=400s is still within cooldown (400-200=200s < 300s) and is suppressed

### Requirement: LRU eviction for fingerprint table
The fingerprint table MUST have a configurable maximum size (default 1000, via `PIPELINE_COOLDOWN_MAX_ENTRIES`). When the table is full, the oldest fingerprint (by last_seen) MUST be evicted.

#### Scenario: Table full triggers eviction
- **WHEN** the fingerprint table has 1000 entries and a new fingerprint arrives
- **THEN** the oldest entry is evicted and the new fingerprint is recorded

### Requirement: Fingerprint includes log body prefix
For events with logs, the fingerprint MUST include the first 60 characters of the last log body. This ensures different error types from the same workload get distinct fingerprints.

#### Scenario: Different errors produce different fingerprints
- **WHEN** two events from the same pod have different error messages ("OOMKilled" vs "connection refused")
- **THEN** they produce different fingerprints and are both investigated
