## ADDED Requirements

### Requirement: MCP client implements the SDK MCPConnector Protocol
The built-in `MCPClientManager` MUST implement the `octantis_plugin_sdk.MCPConnector` Protocol. Its `setup(config)` MUST establish the configured SSE connections. Its `teardown()` MUST close all SSE sessions. `get_tools()` MUST return a list of SDK `Tool` instances.

#### Scenario: MCP client satisfies MCPConnector Protocol
- **WHEN** the Plugin Registry loads the MCP client
- **THEN** `isinstance(mcp_client, MCPConnector)` returns `True`

### Requirement: MCP client registers via the octantis.mcp entry point
The MCP client MUST be declared in `pyproject.toml` under the `octantis.mcp` entry-point group with plugin name `grafana-mcp` (for the Grafana-specific connector) and any additional built-in connectors registered with their own stable names. `main.py` MUST NOT import the MCP client directly.

#### Scenario: MCP client discovered via entry point
- **WHEN** Octantis starts
- **THEN** the Plugin Registry discovers the built-in MCP connector through `octantis.mcp` and `main.py` contains no direct MCP-client import

### Requirement: MCP slot count is subject to plan gating
The number of MCPConnector plugins that may be loaded MUST be bounded by the resolved tier (free=1, pro=3, enterprise=unlimited). When the limit is exceeded, the `PlanGatingEngine` MUST reject startup before any MCP connection is attempted.

#### Scenario: Free tier with two MCP connectors rejected before connect
- **WHEN** a free-tier deployment has two MCPConnector plugins installed
- **THEN** startup fails with a plan-gating error and no SSE connection is opened
