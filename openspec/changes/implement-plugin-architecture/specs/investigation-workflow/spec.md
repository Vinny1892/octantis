## ADDED Requirements

### Requirement: Workflow runs under the runtime dispatcher
Investigation workflows MUST be invoked by the runtime dispatcher selected by `OCTANTIS_MODE`. In `standalone` mode the dispatcher MUST schedule workflows concurrently via `asyncio.TaskGroup` bounded by `OCTANTIS_WORKERS`. In `worker` mode the dispatcher MUST invoke the workflow from a Redpanda consumer loop.

#### Scenario: Standalone schedules concurrent workflows
- **WHEN** five events pass the processor chain in standalone mode
- **THEN** five workflows execute concurrently under the shared semaphore

#### Scenario: Worker mode invokes workflow per consumed message
- **WHEN** a worker consumes a message from Redpanda
- **THEN** exactly one workflow is invoked and the message is not ACKed until the workflow completes

### Requirement: Workflows are idempotent for crash recovery
An investigation workflow MUST produce the same observable outcomes when executed multiple times with the same input `Event`. Notifier invocations MUST carry the `event_id` to enable downstream deduplication by operators.

#### Scenario: Re-executed workflow after worker crash
- **WHEN** a worker dies mid-workflow and Redpanda redelivers the message to another worker
- **THEN** the redelivered workflow runs from scratch and produces an equivalent `InvestigationResult` for the same `event_id`

### Requirement: Workflow tolerates MCP degradation
When an `MCPConnector`'s tool invocation fails or the connector reports degraded state, the workflow MUST continue with the remaining available tools, set `mcp_degraded=True` on the `InvestigationResult`, and propagate that flag to notifiers.

#### Scenario: MCP connector returns no tools
- **WHEN** an MCPConnector's `get_tools()` returns an empty list during a workflow
- **THEN** the workflow proceeds with remaining tools, sets `mcp_degraded=True`, and each notifier receives the degraded flag
