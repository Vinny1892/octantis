## ADDED Requirements

### Requirement: Docker MCP connection via SSE
The system SHALL connect to a Docker MCP server when `DOCKER_MCP_URL` is configured. The connection MUST use SSE and MUST be registered in the MCP registry under the `"platform"` slot. Optional authentication headers MUST be configurable via `DOCKER_MCP_HEADERS` (JSON-encoded string).

#### Scenario: Docker MCP configured and connected
- **WHEN** `DOCKER_MCP_URL` is set to a valid SSE endpoint
- **THEN** the system establishes an SSE connection, discovers available tools, and registers them in the platform slot
- **AND** logs `mcp.connected` with server name, URL, and tool count

#### Scenario: Docker MCP not configured
- **WHEN** `DOCKER_MCP_URL` is not set
- **THEN** the system proceeds without Docker MCP tools and logs `mcp.skipped` at DEBUG level

#### Scenario: Docker MCP unreachable at startup
- **WHEN** `DOCKER_MCP_URL` is set but the server is unreachable
- **THEN** the system retries with exponential backoff up to `MCP_RETRY_MAX_ATTEMPTS` times
- **AND** if all retries exhausted, the system exits with a non-zero status code

### Requirement: Docker MCP tools available to LLM
When Docker MCP is connected, the investigate node MUST receive Docker MCP tools alongside any other configured MCP tools. The LLM MUST be able to call tools for container inspection, container logs, and resource statistics.

#### Scenario: Docker MCP tools in investigation
- **WHEN** a trigger event enters the investigate node with Docker MCP connected
- **THEN** `get_tools()` returns Docker MCP tools in addition to other configured MCP tools
- **AND** the LLM can call Docker container inspection, logs, and stats tools

### Requirement: Docker MCP graceful degradation at runtime
When the Docker MCP connection drops during an active investigation, the system MUST catch the connection error, complete the investigation with remaining MCPs or trigger data only, and set `mcp_degraded: true` on the `InvestigationResult`.

#### Scenario: Docker MCP drops mid-investigation
- **WHEN** a Docker MCP tool call fails during an investigation
- **THEN** the error is caught, logged as `mcp.query_error`, and the investigation continues with remaining tools
- **AND** `mcp_degraded` is set to `true`

#### Scenario: Only Docker MCP configured and it is down
- **WHEN** only Docker MCP is configured and it becomes unreachable
- **THEN** the LLM investigates with trigger event data only (degraded mode)
