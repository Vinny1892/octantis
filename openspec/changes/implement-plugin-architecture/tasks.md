## 1. Phase 1 — SDK + Registry + Protocols

- [x] 1.1 Scaffold `octantis-plugin-sdk` package (separate `pyproject.toml`, Apache-2.0 LICENSE, `src/octantis_plugin_sdk/`)
- [x] 1.2 Define 5 `typing.Protocol` classes (Storage, MCPConnector, Processor, Notifier, UIProvider) with `@runtime_checkable`
- [x] 1.3 Define shared types (`Event`, `InvestigationResult`, `Tool`, `PluginMetadata`) as frozen dataclasses
- [x] 1.4 Add SDK unit tests (Protocol conformance, type immutability)
<!-- 1.5 moved to Phase 6 (6.13) — publish SDK only after Protocols are validated by Phases 2-5 -->

- [x] 1.6 Implement `PluginRegistry` with `importlib.metadata.entry_points()` discovery
- [x] 1.7 Implement fixed load order (Storage → MCP → Processors → Notifiers → UI) with processor priority sort
- [x] 1.8 Implement duplicate-name detection with startup-fail error
- [x] 1.9 Implement reverse-order teardown with error isolation
- [x] 1.10 Emit structured lifecycle logs (discovered, loaded, setup_started/completed, teardown_started/completed)
- [x] 1.11 Register at least one built-in plugin via entry point as end-to-end smoke (pick `trigger-filter`)
- [x] 1.12 Registry unit tests: discovery, load order, duplicates, teardown isolation, lifecycle logs
- [x] 1.13 **Phase 1 test review**: re-read existing trigger-filter tests against the new Protocol boundary (no blind "make green")
- [x] 1.14 **Phase 1 docs**: SDK README, Protocol reference (`docs/plugins.md`), AGENTS.md updated (CLAUDE.md not used in this repo)
- [x] 1.15 **Phase 1 gate**: coverage = 94%, 275/275 tests green, docs review completed

## 2. Phase 2 — Refactor built-in components to Protocols + entry points

- [x] 2.1 Split OTLP gRPC into its own `Ingester` plugin (`otlp-grpc-ingester`), register under `octantis.ingesters` (Fork C=1: per-transport plugin, SRP)
- [x] 2.2 Split OTLP HTTP into its own `Ingester` plugin (`otlp-http-ingester`), register under `octantis.ingesters` (Fork C=1: per-transport plugin, SRP)
- [x] 2.3 Refactor `otlp-ingester-orchestrator` to consume ingesters from the registry (no direct imports); merge events from multiple Ingester plugins into the pipeline
- [x] 2.4 Refactor `otlp-parser` to emit SDK `Event` (keep module importable without runtime side effects)
- [x] 2.5 Split `MCPClientManager` into per-server MCPConnector plugins: `grafana-mcp`, `k8s-mcp`, `docker-mcp`, `aws-mcp`, each registered under `octantis.mcp` (Fork B=1: one connector per server, SRP)
- [x] 2.6 Refactor `trigger-filter` to implement `Processor` with priority=100, register under `octantis.processors`
- [x] 2.7 Refactor `fingerprint-cooldown` to implement `Processor` with priority=200, register under `octantis.processors`
- [x] 2.8 Refactor notifiers to implement `Notifier`, register under `octantis.notifiers`
- [x] 2.9 Strip all direct component imports from `main.py`; wire everything via the registry (depends on 2.1/2.2/2.5)
- [x] 2.10 Update `pyproject.toml` with all entry-point declarations aligned to the split plugins (per-transport Ingesters + per-server MCPConnectors)
- [x] 2.11 **Phase 2 test review** (mandatory, per-component): for each refactored module, re-read its tests and adjust them to exercise the Protocol boundary — not just make the suite green
- [x] 2.12 Run the full test suite and verify 333+ tests pass with coverage ≥ 94%
- [ ] 2.13 Manual end-to-end smoke: send OTLP events → investigation runs → notifier fires, identical to pre-refactor behavior
- [x] 2.14 **Phase 2 docs**: update architecture diagrams, component inventory, `AGENTS.md` (entry-point model), specs updated (Ingester Protocol + per-server MCP)
- [ ] 2.15 **Phase 2 gate**: all reviews checked off, CI green, manual smoke passing — only then close the phase

## 3. Phase 3 — Plan gating (JWT Ed25519 + PlanGatingEngine)

- [ ] 3.1 Generate an Ed25519 keypair; commit the public key to `src/octantis/licensing/public_key.pem`; store the private key securely (offline)
- [ ] 3.2 Implement JWT validator (PyJWT + cryptography) that verifies signature, `iss`, `iat`, `exp` offline
- [ ] 3.3 Implement `PlanGatingEngine` with tier rules (free: 1 MCP / 1 notifier / 0 UI; pro: 3/3/0; enterprise: unlimited/unlimited/1)
- [ ] 3.4 Wire gating between registry discovery and plugin `setup()` — reject before any external connection
- [ ] 3.5 Emit actionable error logs (tier, limit, installed_count, plugin_names, remediation) without leaking JWT contents
- [ ] 3.6 Handle missing `OCTANTIS_LICENSE_JWT` as free tier
- [ ] 3.7 Add export of `octantis_plan_tier_info` and `octantis_plan_gating_violations_total` metrics
- [ ] 3.8 Unit tests: valid JWTs (all three tiers), tampered JWT, expired JWT, missing JWT, unknown issuer, each tier limit edge case
- [ ] 3.9 **Phase 3 test review**: confirm tests cover every documented gating scenario (not just happy path)
- [ ] 3.10 **Phase 3 docs**: write `LICENSING.md` (tier matrix + FAQ), operator guide on obtaining and installing a license JWT
- [ ] 3.11 **Phase 3 gate**: coverage ≥ 94%, CI green, docs review — only then close the phase

## 4. Phase 4 — Concurrent standalone runtime

- [ ] 4.1 Implement standalone runner using `asyncio.TaskGroup` + semaphore bounded by `OCTANTIS_WORKERS` (default 20)
- [ ] 4.2 Implement `OCTANTIS_MODE` dispatcher; `standalone` is the default
- [ ] 4.3 Reject unknown `OCTANTIS_MODE` values at startup with a clear error
- [ ] 4.4 Export `octantis_standalone_active_workflows` and `octantis_standalone_semaphore_capacity` metrics
- [ ] 4.5 Concurrency tests: 5 events → 5 parallel workflows; 100 events with `OCTANTIS_WORKERS=5` → semaphore-bounded; cancellation propagation
- [ ] 4.6 **Phase 4 test review**: verify tests actually exercise the TaskGroup/semaphore boundary and race-condition scenarios
- [ ] 4.7 Manual smoke: burst 20 events in standalone → observe metrics and logs show parallel execution
- [ ] 4.8 **Phase 4 docs**: `OCTANTIS_WORKERS` tuning guide, standalone performance expectations
- [ ] 4.9 **Phase 4 gate**: coverage ≥ 94%, CI green, docs review — only then close the phase

## 5. Phase 5 — Distributed runtime (Redpanda ingester + worker)

- [ ] 5.1 Decide Kafka client library (`aiokafka` vs `confluent-kafka`) per the open question in design.md; add dependency
- [ ] 5.2 Implement `ingester` runner: consume events from Storage plugins, serialize, produce to `octantis.events` topic
- [ ] 5.3 Implement `worker` runner: consume from `octantis.events`, invoke workflow, ACK only on successful completion
- [ ] 5.4 Implement exponential-backoff connect retry for ingester (2s, 4s, 8s, …, 60s cap) with exit-non-zero budget
- [ ] 5.5 Add env vars `OCTANTIS_REDPANDA_BROKERS`, `OCTANTIS_REDPANDA_TOPIC`, `OCTANTIS_REDPANDA_CONSUMER_GROUP`
- [ ] 5.6 Export distributed-mode metrics (published/consumed/redelivered/consumer_lag)
- [ ] 5.7 Add Redpanda as an optional Helm subchart; ingester/worker Deployments in the main chart
- [ ] 5.8 Integration tests with a real Redpanda container (testcontainers): end-to-end publish/consume, worker crash → redelivery, idempotency
- [ ] 5.9 Workflow idempotency review: for each existing workflow step, confirm safe re-execution on the same `event_id`
- [ ] 5.10 **Phase 5 test review**: confirm integration tests cover redelivery, consumer-group rebalance, and idempotency — not just happy path
- [ ] 5.11 **Phase 5 docs**: distributed deployment guide, Helm values reference, Redpanda sizing, troubleshooting runbook
- [ ] 5.12 **Phase 5 gate**: coverage ≥ 94%, CI green, integration tests green, docs review — only then close the phase

## 6. Phase 6 — License migration to AGPL-3.0

- [ ] 6.1 Replace `LICENSE` with the canonical AGPL-3.0 text
- [ ] 6.2 Add SPDX header `# SPDX-License-Identifier: AGPL-3.0-or-later` to every `.py` file under `src/octantis/`
- [ ] 6.3 Add SPDX header `# SPDX-License-Identifier: Apache-2.0` to every `.py` file under `src/octantis_plugin_sdk/`
- [ ] 6.4 Update core `pyproject.toml`: `license`, Trove classifier
- [ ] 6.5 Update Helm `Chart.yaml` `annotations.licenses`
- [ ] 6.6 Update README license badge and SDK mention (SDK is Apache-2.0)
- [ ] 6.7 Write `LICENSING.md` (self-host vs SaaS, SDK Apache-2.0, plugin-author FAQ)
- [ ] 6.8 Add CI job: license-header linter (fails on missing/mismatched SPDX)
- [ ] 6.9 Add CI job: `pip-licenses` audit for core (fail on AGPL-incompatible) and SDK (fail on anything more restrictive than Apache-compatible)
- [ ] 6.10 **Phase 6 test review**: license-header linter tested against positive and negative fixtures; pip-licenses audit tested with a deliberately incompatible dep in a fixture
- [ ] 6.11 **Phase 6 docs**: confirm every README link resolves, `LICENSING.md` is linked from README, FAQ answers the common AGPL questions
- [ ] 6.12 **Phase 6 gate**: CI license jobs green, docs review — only then close the phase
- [ ] 6.13 Publish `octantis-plugin-sdk` (version set by cumulative Protocol stability) to TestPyPI, verify install, then PyPI — requires maintainer credentials

## 7. Cross-phase CI and policy

- [ ] 7.1 Enforce coverage floor ≥ 94% in CI (fail the build below threshold)
- [ ] 7.2 Add PR template checklist mirroring the per-phase gate (tests reviewed, docs updated, license headers present)
- [ ] 7.3 Decide and implement the "tests were reviewed" enforcement mechanism (required label, checklist, or CODEOWNERS) per design.md open question
- [ ] 7.4 Cross-reference audit: PRD 005, Tech Spec 005, and all modified capability specs link to each other consistently
- [ ] 7.5 Final launch checklist walk-through (Tech Spec 005 §11 — Implementation / Tests / Documentation blocks)
