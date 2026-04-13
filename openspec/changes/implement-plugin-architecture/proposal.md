## Why

Octantis today wires components via direct imports in `main.py`, which blocks the monetization model defined in the Business Model (free/pro/enterprise tiers with plan-gated features) and prevents third parties from shipping plugins without forking. Without a plugin architecture, the open-core strategy, the distributed deployment mode, and the AGPL-3.0 relicensing described in Tech Spec 005 cannot ship — and every phase of the rollout explicitly requires test and documentation review that the current structure cannot enforce.

## What Changes

- Introduce 6 Protocol interfaces (Ingester, Storage, MCPConnector, Processor, Notifier, UIProvider) in a new **Apache-2.0 SDK package** (`octantis-plugin-sdk`) published to PyPI. "Ingester" is the Octantis-side concept for an event source (to avoid conflating with the OTel Collector's "receiver" pipeline stage).
- Add a **Plugin Registry** that discovers plugins via Python entry points (`octantis.ingesters`, `octantis.storage`, `octantis.mcp`, `octantis.processors`, `octantis.notifiers`, `octantis.ui`) with a fixed load order by type.
- Refactor **all existing built-in components** (OTLP ingesters, MCP client, trigger filter, fingerprint cooldown, investigator, metrics, notifiers) to implement the Protocols and register via entry points — zero direct imports in `main.py`. **BREAKING** for anyone wiring internal modules directly (pre-0.0.1, no external users).
- Add **PlanGatingEngine** with JWT Ed25519 license validation (offline-verifiable) enforcing free (1 MCP, 1 notifier), pro (3 MCPs, 3 notifiers), and enterprise (unlimited + UI provider) tiers.
- Add **dual deployment modes** via `OCTANTIS_MODE` env var: `standalone` (asyncio TaskGroup + semaphore for concurrent investigations, zero external deps) and `ingester`/`worker` (Redpanda-backed distributed processing).
- **Relicense** Octantis core from current license to **AGPL-3.0**; SDK stays Apache-2.0. Update `LICENSE`, file headers, `pyproject.toml`, Helm `Chart.yaml`, README badges, and add `LICENSING.md`.
- **Mandatory per-phase review gates** (per Tech Spec 005 §11): every phase ships only with (a) test suite reviewed and updated against the new Protocol boundaries and (b) affected documentation updated. Coverage ≥ 94% enforced in CI.

## Capabilities

### New Capabilities

- `plugin-sdk`: The Apache-2.0 `octantis-plugin-sdk` package — exports the 6 Protocols (Ingester, Storage, MCPConnector, Processor, Notifier, UIProvider), shared types (Event, InvestigationResult, Tool), and the plugin author contract. Becomes the stable public surface for third-party plugin authors.
- `plugin-registry`: Entry-point-based plugin discovery, fixed load-order lifecycle (Ingesters → Storage → MCP → Processors → Notifiers → UI), duplicate detection, and structured lifecycle logging.
- `plan-gating`: JWT Ed25519 license validation (offline) and `PlanGatingEngine` enforcing tier rules (MCP slots, notifier slots, UI provider availability) at registry load time with clear operator-facing errors.
- `distributed-runtime`: `OCTANTIS_MODE` dispatcher with `standalone` (concurrent asyncio), `ingester` (publishes events to Redpanda), and `worker` (consumes from Redpanda, idempotent redelivery) modes sharing the same binary.
- `license-migration`: AGPL-3.0 relicensing of core with dual-license documentation and file-header enforcement.

### Modified Capabilities

- `otlp-grpc-ingester`: MUST implement the SDK `Ingester` Protocol (Octantis-side event source) and register via entry point instead of direct instantiation in `main.py`. Distinct from the OpenTelemetry Collector's "OTLP receiver" pipeline stage.
- `otlp-http-ingester`: MUST implement the SDK `Ingester` Protocol and register via entry point.
- `otlp-ingester-orchestrator`: MUST consume ingesters from the Plugin Registry instead of direct imports and respect load order.
- `otlp-parser`: MUST expose its parse output via the SDK `Event` type shared with plugin authors.
- `mcp-client`: MUST implement the SDK `MCPConnector` Protocol and be subject to plan-gated MCP slot limits.
- `trigger-filter`: MUST implement the SDK `Processor` Protocol with configurable `priority` (default 100) and register via entry point.
- `fingerprint-cooldown`: MUST implement the SDK `Processor` Protocol with configurable `priority` (default 200) and register via entry point.
- `investigation-workflow`: MUST run under the new runtime dispatcher (standalone concurrent via TaskGroup+semaphore, or worker-mode via Redpanda consumption) and tolerate MCP degradation (`mcp_degraded=True`).
- `investigation-metrics`: MUST export new plugin-registry, plan-gating, and distributed-mode metrics in addition to existing investigation metrics.

## Impact

- **Code**: new `src/octantis_plugin_sdk/` (separate package), new `src/octantis/plugins/registry.py`, new `src/octantis/licensing/` (JWT validator + PlanGatingEngine), new `src/octantis/runtime/` (mode dispatcher, standalone concurrent runner, Redpanda ingester/worker). Every existing component under `src/octantis/` refactored to Protocol implementations and entry-point registered in `pyproject.toml`.
- **APIs**: new public SDK surface (6 Protocols, shared types) — stable contract for plugin authors. Entry-point group names (`octantis.ingesters`, `octantis.storage`, `octantis.mcp`, `octantis.processors`, `octantis.notifiers`, `octantis.ui`) are frozen once shipped.
- **Dependencies**: adds `pyjwt[crypto]` (Ed25519), `cryptography`, and (distributed mode only) a Redpanda/Kafka client (`aiokafka` or `confluent-kafka`). Removes no existing dependencies.
- **Infrastructure**: Helm chart gains ingester/worker deployments and Redpanda dependency (optional, standalone remains zero-dep). New env vars: `OCTANTIS_MODE`, `OCTANTIS_WORKERS`, `OCTANTIS_LICENSE_JWT`, `OCTANTIS_REDPANDA_BROKERS`.
- **Licensing**: repository relicenses to AGPL-3.0 (from current). SDK package ships Apache-2.0. `LICENSING.md` documents the dual model; README badges and `pyproject.toml` classifiers updated.
- **Testing**: all 254 existing tests reviewed against new Protocol boundaries (no blind "make green"); coverage floor ≥ 94%. New suites for registry, plan gating, JWT validation, concurrency, and Redpanda integration (real container).
- **Documentation**: `README.md`, `CLAUDE.md`, `LICENSING.md`, SDK reference docs, `CONTRIBUTING.md` plugin-author guide, operator guides (standalone tuning, distributed deployment, Helm values, Redpanda sizing, troubleshooting), AGPL FAQ, and PRD/Tech Spec cross-references all reviewed and updated per phase.
- **Rollout**: 6 sequential phases (SDK+Registry → built-in refactor → plan gating → concurrent standalone → distributed → license migration) — each blocked until tests + docs review complete.
