## ADDED Requirements

### Requirement: OCTANTIS_MODE selects the runtime topology
The runtime dispatcher MUST read `OCTANTIS_MODE` at startup and route to one of three runners: `standalone` (default), `ingester`, or `worker`. An unknown value MUST cause startup to fail with an error listing the valid options.

#### Scenario: Default is standalone
- **WHEN** `OCTANTIS_MODE` is unset
- **THEN** the runtime runs in standalone mode

#### Scenario: Invalid mode rejected
- **WHEN** `OCTANTIS_MODE=foo`
- **THEN** startup fails with `invalid OCTANTIS_MODE=foo; expected one of: standalone, ingester, worker`

### Requirement: Standalone mode processes events concurrently
In `standalone` mode the runtime MUST process incoming events concurrently using `asyncio.TaskGroup` bounded by a semaphore of size `OCTANTIS_WORKERS` (default 20). The mode MUST have zero external-service dependencies beyond what plugins themselves require.

#### Scenario: Five events processed in parallel
- **WHEN** five events arrive within 100ms in standalone mode with `OCTANTIS_WORKERS=20`
- **THEN** five investigation workflows execute concurrently and all emit their `investigation.started` log within the same event loop iteration

#### Scenario: Semaphore bounds concurrency
- **WHEN** 100 events arrive in standalone mode with `OCTANTIS_WORKERS=5`
- **THEN** at most 5 workflows execute at any moment; the remaining 95 queue and execute as slots free

### Requirement: Ingester mode publishes events to Redpanda
In `ingester` mode the runtime MUST receive events via its configured Ingester plugins and publish them to a Redpanda topic (default `octantis.events`) using the brokers in `OCTANTIS_REDPANDA_BROKERS`. The ingester MUST NOT execute investigation workflows. On broker-connection failure the ingester MUST retry with exponential backoff (2s, 4s, 8s, capped at 60s); after repeated failures exhausting a configurable budget, it MUST exit non-zero.

#### Scenario: Event published on receive
- **WHEN** the ingester receives an OTLP event in `ingester` mode
- **THEN** the event is serialized and produced to the `octantis.events` topic and no investigation workflow runs in-process

#### Scenario: Broker down triggers backoff
- **WHEN** Redpanda is unreachable
- **THEN** the ingester retries connection with delays 2s, 4s, 8s, …, 60s and logs each attempt

### Requirement: Worker mode consumes events with idempotent redelivery
In `worker` mode the runtime MUST consume from the `octantis.events` Redpanda topic as part of a configurable consumer group (default `octantis.workers`). The worker MUST NOT ACK a message until the investigation workflow completes successfully. If the process dies mid-workflow, Redpanda MUST redeliver the message to another worker in the group, and workflows MUST be safe to execute from scratch on the same event.

#### Scenario: Worker crash triggers redelivery
- **WHEN** a worker dies while processing a message and two other workers are in the consumer group
- **THEN** Redpanda redelivers the un-ACKed message to another worker within the configured session timeout and the workflow runs again from scratch

#### Scenario: Successful completion ACKs
- **WHEN** a worker completes a workflow successfully
- **THEN** the message offset is committed and is not redelivered
