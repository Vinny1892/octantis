## ADDED Requirements

### Requirement: AWS MCP connection via SSE
The system SHALL connect to an AWS MCP server when `AWS_MCP_URL` is configured. The connection MUST use SSE and MUST be registered in the MCP registry under the `"platform"` slot. Optional authentication headers MUST be configurable via `AWS_MCP_HEADERS` (JSON-encoded string).

#### Scenario: AWS MCP configured and connected
- **WHEN** `AWS_MCP_URL` is set to a valid SSE endpoint
- **THEN** the system establishes an SSE connection, discovers available tools, and registers them in the platform slot
- **AND** logs `mcp.connected` with server name, URL, and tool count

#### Scenario: AWS MCP not configured
- **WHEN** `AWS_MCP_URL` is not set
- **THEN** the system proceeds without AWS MCP tools and logs `mcp.skipped` at DEBUG level

#### Scenario: AWS MCP unreachable at startup
- **WHEN** `AWS_MCP_URL` is set but the server is unreachable
- **THEN** the system retries with exponential backoff up to `MCP_RETRY_MAX_ATTEMPTS` times
- **AND** if all retries exhausted, the system exits with a non-zero status code

### Requirement: AWS MCP tools available to LLM
When AWS MCP is connected, the investigate node MUST receive AWS MCP tools alongside any other configured MCP tools. The LLM MUST be able to call tools for EC2 instance inspection, CloudWatch metrics, and ECS task status.

#### Scenario: AWS MCP tools in investigation
- **WHEN** a trigger event enters the investigate node with AWS MCP connected
- **THEN** `get_tools()` returns AWS MCP tools in addition to other configured MCP tools
- **AND** the LLM can call EC2 describe, CloudWatch query, and ECS task status tools

### Requirement: AWS MCP graceful degradation at runtime
When the AWS MCP connection drops during an active investigation, the system MUST catch the connection error, complete the investigation with remaining MCPs or trigger data only, and set `mcp_degraded: true` on the `InvestigationResult`.

#### Scenario: AWS MCP drops mid-investigation
- **WHEN** an AWS MCP tool call fails during an investigation
- **THEN** the error is caught, logged as `mcp.query_error`, and the investigation continues with remaining tools
- **AND** `mcp_degraded` is set to `true`

#### Scenario: Only AWS MCP configured and it is down
- **WHEN** only AWS MCP is configured and it becomes unreachable
- **THEN** the LLM investigates with trigger event data only (degraded mode)

### Requirement: AWS resource not found during investigation
When the LLM queries an AWS resource that does not exist (e.g., terminated EC2 instance), the system MUST return a "not found" result to the LLM and allow the investigation to continue.

#### Scenario: EC2 instance terminated
- **WHEN** the LLM queries an EC2 instance that has been terminated
- **THEN** the tool returns a "not found" result
- **AND** the LLM continues the investigation with available data
