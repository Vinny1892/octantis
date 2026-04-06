## ADDED Requirements

### Requirement: MCP client manager connects to Grafana MCP via SSE
The `MCPClientManager` SHALL establish SSE connections to configured MCP servers at startup. It MUST connect to `GRAFANA_MCP_URL` when configured. It MUST connect to `K8S_MCP_URL` when configured. Each connection MUST discover available tools and log `mcp.connected` with `url` and `tools_count`.

#### Scenario: Successful Grafana MCP connection
- **WHEN** Octantis starts with `GRAFANA_MCP_URL` configured
- **THEN** the system establishes an SSE connection to the Grafana MCP server, discovers available tools, and logs `mcp.connected` with the URL and tool count

#### Scenario: Successful K8s MCP connection
- **WHEN** Octantis starts with `K8S_MCP_URL` configured
- **THEN** the system establishes an SSE connection to the K8s MCP server, discovers available tools, and logs `mcp.connected` with the URL and tool count

#### Scenario: K8s MCP not configured
- **WHEN** Octantis starts without `K8S_MCP_URL`
- **THEN** the system proceeds without K8s MCP tools and logs `mcp.k8s_not_configured` at INFO level

### Requirement: MCP client exposes tools as LangChain tools
The `MCPClientManager` MUST convert all discovered MCP tools to LangChain-compatible tools via `langchain-mcp-adapters`. It MUST expose a `get_tools() -> list[BaseTool]` method that returns all available tools from all connected MCP servers.

#### Scenario: Tools from multiple MCP servers
- **WHEN** both Grafana MCP and K8s MCP are connected
- **THEN** `get_tools()` returns tools from both servers in a single list

#### Scenario: Only Grafana MCP connected
- **WHEN** only Grafana MCP is connected (K8s MCP not configured)
- **THEN** `get_tools()` returns only Grafana MCP tools (PromQL, LogQL)

### Requirement: MCP connection failure enters degraded mode
When an MCP SSE connection fails at startup or drops during runtime, the system MUST log `mcp.connection_failed` at WARNING level with the URL and error. The system MUST NOT crash. The `MCPClientManager` MUST report which servers are unavailable via `get_degraded_servers() -> list[str]`.

#### Scenario: Grafana MCP unreachable at startup
- **WHEN** Octantis starts and cannot connect to `GRAFANA_MCP_URL`
- **THEN** the system logs `mcp.connection_failed`, starts in degraded mode, and `get_tools()` returns an empty list

#### Scenario: MCP connection drops mid-runtime
- **WHEN** the SSE connection to Grafana MCP drops during operation
- **THEN** the system logs `mcp.connection_failed` and reports the server as degraded

### Requirement: MCP authentication via API key
The system MUST authenticate to Grafana MCP using `GRAFANA_MCP_API_KEY`. The API key MUST be passed as a header in the SSE connection. The system MUST fail with a clear error if `GRAFANA_MCP_URL` is set but `GRAFANA_MCP_API_KEY` is not.

#### Scenario: Missing API key
- **WHEN** `GRAFANA_MCP_URL` is configured but `GRAFANA_MCP_API_KEY` is not
- **THEN** the system logs an error at startup indicating the missing API key

### Requirement: MCP query timeout
Each individual MCP query MUST have a configurable timeout (default 10s, via `INVESTIGATION_QUERY_TIMEOUT_SECONDS`). When a query exceeds the timeout, the system MUST cancel it and return a timeout error to the LLM as a tool result.

#### Scenario: MCP query times out
- **WHEN** an MCP query exceeds 10 seconds
- **THEN** the query is cancelled, the LLM receives a timeout error as the tool result, and `mcp.query_timeout` is logged
