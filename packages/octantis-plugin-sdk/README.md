# octantis-plugin-sdk

Plugin SDK for [Octantis](https://github.com/octantis/octantis) — the open-core, OTLP-native incident investigator.

This package defines the stable public contract between Octantis and plugin authors: six Protocol interfaces, shared data types, and the lifecycle they guarantee.

> Octantis uses **"Ingester"** for its event-source Protocol, distinct from the OpenTelemetry Collector's "receiver" pipeline stage. An Ingester plugin lives inside the Octantis process and produces SDK `Event` instances.

- **License**: Apache-2.0 (permissive — your plugin is NOT obligated to be AGPL just because Octantis core is)
- **Stability**: semantic versioning. Breaking changes require a major bump.
- **No runtime deps on Octantis core**: depend on this SDK only.

## Install

```bash
pip install octantis-plugin-sdk
```

## Protocols

Octantis discovers plugins via six Python entry-point groups. Implement the matching Protocol and register under the matching group.

| Protocol         | Entry-point group      | Purpose                                                             |
|------------------|------------------------|---------------------------------------------------------------------|
| `Ingester`       | `octantis.ingesters`   | Event sources (OTLP gRPC, OTLP HTTP, pull scrapers, log tailers).   |
| `Storage`        | `octantis.storage`     | Persistence backends (investigations, cooldown state).              |
| `MCPConnector`   | `octantis.mcp`         | MCP tool providers (Grafana, K8s, Docker, AWS, custom).             |
| `Processor`      | `octantis.processors`  | Event-pipeline stages (trigger filter, cooldown, enrichers).        |
| `Notifier`       | `octantis.notifiers`   | Outbound destinations (Slack, Discord, email, webhook).             |
| `UIProvider`     | `octantis.ui`          | UI surfaces (enterprise tier only).                                 |

## Minimal plugin example

```python
# my_notifier/plugin.py
from octantis_plugin_sdk import Notifier, InvestigationResult

class MyNotifier:
    name = "my-notifier"
    version = "0.1.0"

    def setup(self, config: dict) -> None:
        self._url = config["webhook_url"]

    def teardown(self) -> None:
        pass

    async def send(self, result: InvestigationResult) -> None:
        ...
```

Register in your `pyproject.toml`:

```toml
[project.entry-points."octantis.notifiers"]
my-notifier = "my_notifier.plugin:MyNotifier"
```

## Shared types

- `Event` — the canonical event passed through the pipeline.
- `InvestigationResult` — the output of an investigation workflow.
- `Tool` — an MCP tool exposed to the investigator.
- `PluginMetadata` — optional structured metadata a plugin may expose.

See the Protocol source files for the full contracts.

## Tier limits

Octantis enforces plugin-count limits by license tier at load time:

| Tier       | MCPConnectors | Notifiers | UIProvider |
|------------|---------------|-----------|------------|
| free       | 1             | 1         | 0          |
| pro        | 3             | 3         | 0          |
| enterprise | unlimited     | unlimited | 1          |

Plugin installation is never blocked — only loading beyond your tier's limits is.
