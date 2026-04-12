# Plugin Architecture (Phase 1)

Octantis components are discovered at runtime through the **Plugin Registry**.
Every pipeline stage — event sources, MCP connectors, processors, notifiers,
UI surfaces — is a plugin that implements one of the six Protocols exported
by [`octantis-plugin-sdk`](../packages/octantis-plugin-sdk/README.md).

> **Terminology:** Octantis uses **"Ingester"** for its event-source Protocol,
> distinct from the OpenTelemetry Collector's "receiver" pipeline stage.
> An Octantis Ingester is a plugin inside the Octantis process that produces
> SDK `Event` instances (from OTLP gRPC, OTLP HTTP, Prometheus pull, syslog,
> tailers, etc.).

> **Status:** Phase 1 of the change in `openspec/changes/implement-plugin-architecture/`.
> The SDK, registry, and Protocols are in place. Built-in components are
> refactored to Protocol adapters in Phase 2.

## The six Protocols

| Protocol       | Entry-point group     | Role                                                         |
|----------------|-----------------------|--------------------------------------------------------------|
| `Ingester`     | `octantis.ingesters`  | Event sources (OTLP gRPC/HTTP, pull scrapers, tailers)       |
| `Storage`      | `octantis.storage`    | Persistence backends (investigations, cooldown state)        |
| `MCPConnector` | `octantis.mcp`        | MCP tool providers (one plugin per server: grafana/k8s/...)  |
| `Processor`    | `octantis.processors` | Pipeline stages (filters, cooldowns)                         |
| `Notifier`     | `octantis.notifiers`  | Outbound destinations                                        |
| `UIProvider`   | `octantis.ui`         | UI surfaces (enterprise)                                     |

Each Protocol declares `setup(config: dict)` and `teardown()` lifecycle hooks
plus role-specific methods. See
[`packages/octantis-plugin-sdk/src/octantis_plugin_sdk/protocols.py`](../packages/octantis-plugin-sdk/src/octantis_plugin_sdk/protocols.py)
for the full contract.

## Load order

The registry loads plugins in this fixed order:

```
Ingesters → Storage → MCP → Processors → Notifiers → UI
```

Processors within their group are further sorted by their integer
`priority` attribute (lower runs first). Built-in defaults:

| Processor             | Priority |
|-----------------------|----------|
| `trigger-filter`      | 100      |
| `fingerprint-cooldown`| 200      |

Third-party processors pick any integer to slot in between or outside.

## Writing a plugin

1. Depend on `octantis-plugin-sdk` (Apache-2.0, no copyleft).
2. Implement the Protocol for your role.
3. Register an entry point under the matching group in your package's
   `pyproject.toml`.

Minimal notifier example:

```python
# my_notifier/plugin.py
from octantis_plugin_sdk import InvestigationResult

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

```toml
# my_notifier/pyproject.toml
[project.entry-points."octantis.notifiers"]
my-notifier = "my_notifier.plugin:MyNotifier"
```

Install with `pip install my-notifier` alongside Octantis — the registry
picks it up at startup.

## Lifecycle logs

The registry emits structured logs (via `structlog`) for every lifecycle
event. Tail these during debugging:

```
plugin.loaded                plugin_name=... plugin_type=... plugin_version=... source_package=...
plugin.registry.discovered   total=N by_type={...}
plugin.setup_started         plugin_name=...
plugin.setup_completed       plugin_name=... duration_ms=...
plugin.teardown_started      plugin_name=...
plugin.teardown_completed    plugin_name=... duration_ms=...
plugin.setup_failed          plugin_name=... error=...
plugin.teardown_failed       plugin_name=... error=...
```

A `teardown_failed` does not abort shutdown — the registry logs it and
continues tearing down the remaining plugins in reverse load order.

## Failure modes

| Failure                                   | Effect                                                       |
|-------------------------------------------|--------------------------------------------------------------|
| Plugin entry point cannot be imported     | Startup aborts with `PluginLoadError` naming the package     |
| Plugin class fails to instantiate         | Startup aborts with `PluginLoadError`                        |
| Plugin does not satisfy its Protocol      | Startup aborts with `PluginLoadError` naming the Protocol    |
| Two plugins register the same name        | Startup aborts with `DuplicatePluginError` naming both pkgs  |
| `setup()` raises                          | Startup aborts; already-setup plugins are torn down cleanly  |
| `teardown()` raises                       | Error logged; remaining plugins still torn down              |

## See also

- Tech Spec 005 — `docs/tech-specs/tech-spec-005-plugin-architecture.md`
- SDK package README — `packages/octantis-plugin-sdk/README.md`
- Change proposal — `openspec/changes/implement-plugin-architecture/proposal.md`
