## MODIFIED Requirements

### Requirement: MCP client manager connects to MCP servers via SSE registry
The `MCPClientManager` SHALL establish SSE connections to configured MCP servers at startup using a registry pattern. It MUST accept a list of `MCPServerConfig` objects, each declaring `name`, `slot` (observability or platform), `url`, and `headers`. It MUST validate slot limits: minimum 1 MCP total, maximum 1 per slot. Each connection MUST discover available tools and log `mcp.connected` with `url` and `tools_count`.

#### Scenario: Successful Grafana MCP connection
- **WHEN** Octantis starts with a `MCPServerConfig` for Grafana (slot=observability)
- **THEN** the system establishes an SSE connection, discovers available tools, and logs `mcp.connected` with the URL and tool count

#### Scenario: Successful Docker MCP connection
- **WHEN** Octantis starts with a `MCPServerConfig` for Docker (slot=platform)
- **THEN** the system establishes an SSE connection, discovers available tools, and logs `mcp.connected` with the URL and tool count

#### Scenario: Successful AWS MCP connection
- **WHEN** Octantis starts with a `MCPServerConfig` for AWS (slot=platform)
- **THEN** the system establishes an SSE connection, discovers available tools, and logs `mcp.connected` with the URL and tool count

#### Scenario: K8s MCP not configured
- **WHEN** Octantis starts without a K8s MCP config
- **THEN** the system proceeds without K8s MCP tools and logs `mcp.skipped` at DEBUG level

### Requirement: MCP client exposes tools as LangChain tools
The `MCPClientManager` MUST convert all discovered MCP tools to LangChain-compatible tools via `langchain-mcp-adapters`. It MUST expose a `get_tools() -> list[BaseTool]` method that returns all available tools from all connected MCP servers.

#### Scenario: Tools from multiple MCP servers
- **WHEN** both Grafana MCP (observability) and Docker MCP (platform) are connected
- **THEN** `get_tools()` returns tools from both servers in a single list

#### Scenario: Only one MCP connected
- **WHEN** only Grafana MCP is connected
- **THEN** `get_tools()` returns only Grafana MCP tools

### Requirement: MCP slot validation at startup
The `MCPClientManager` MUST validate MCP configurations at startup. It MUST reject configurations with zero MCPs (startup error). It MUST reject configurations with 2 or more MCPs in the same slot (startup error). It MUST accept configurations with 1 observability + 1 platform MCP. It MUST accept configurations with only 1 MCP from either slot.

#### Scenario: Zero MCPs configured
- **WHEN** no MCP server configs are provided
- **THEN** the system logs an error `"no MCP servers configured — at least one is required"` and exits with non-zero status

#### Scenario: Two observability MCPs configured
- **WHEN** two configs with slot=observability are provided (e.g., Grafana + ELK)
- **THEN** the system logs an error `"multiple observability MCPs configured — limit is 1 per slot"` and exits with non-zero status

#### Scenario: Two platform MCPs configured
- **WHEN** two configs with slot=platform are provided (e.g., Docker + AWS)
- **THEN** the system logs an error `"multiple platform MCPs configured — limit is 1 per slot"` and exits with non-zero status

#### Scenario: One observability + one platform accepted
- **WHEN** one observability config and one platform config are provided
- **THEN** the system proceeds with both MCPs and logs `mcp.slot_validation` with counts

#### Scenario: Single MCP accepted
- **WHEN** only one MCP config is provided (either slot)
- **THEN** the system proceeds and connects to that MCP

### Requirement: MCP connection failure enters degraded mode
When an MCP SSE connection fails at startup after exhausting retries or drops during runtime, the system MUST log `mcp.connection_failed` at WARNING level with the URL and error. The `MCPClientManager` MUST report which servers are unavailable via `get_degraded_servers() -> list[str]`.

#### Scenario: MCP unreachable at startup
- **WHEN** Octantis starts and cannot connect to a configured MCP server after all retries
- **THEN** the system exits with non-zero status

#### Scenario: MCP connection drops mid-runtime
- **WHEN** the SSE connection to an MCP server drops during operation
- **THEN** the system logs `mcp.connection_failed` and reports the server as degraded

### Requirement: MCP startup retry with exponential backoff
When an MCP SSE connection fails at startup, the system MUST retry with exponential backoff. Default: 3 attempts with base 2 seconds (2s, 4s, 8s). If all retries are exhausted, the system MUST exit with non-zero status.

#### Scenario: MCP connection succeeds on retry
- **WHEN** the first connection attempt fails but the second succeeds
- **THEN** the system logs `mcp.retry` with attempt number and wait time, then connects successfully

#### Scenario: MCP retries exhausted
- **WHEN** all 3 connection attempts fail
- **THEN** the system logs `mcp.retry_exhausted` with server name and attempt count
- **AND** exits with non-zero status

### Requirement: MCP authentication via headers
The system MUST support authentication headers for each MCP server via the `headers` field in `MCPServerConfig`. Grafana MCP MUST continue to use `GRAFANA_MCP_API_KEY` passed as a Bearer token header.

#### Scenario: Grafana MCP with API key
- **WHEN** `GRAFANA_MCP_URL` and `GRAFANA_MCP_API_KEY` are configured
- **THEN** the MCPServerConfig includes `headers={"Authorization": "Bearer <key>"}`

#### Scenario: Missing Grafana API key
- **WHEN** `GRAFANA_MCP_URL` is configured but `GRAFANA_MCP_API_KEY` is not
- **THEN** the system logs an error indicating the missing API key

### Requirement: MCP query timeout
Each individual MCP query MUST have a configurable timeout (default 10s, via `INVESTIGATION_QUERY_TIMEOUT_SECONDS`). When a query exceeds the timeout, the system MUST cancel it and return a timeout error to the LLM as a tool result.

#### Scenario: MCP query times out
- **WHEN** an MCP query exceeds 10 seconds
- **THEN** the query is cancelled, the LLM receives a timeout error as the tool result, and `mcp.query_timeout` is logged
