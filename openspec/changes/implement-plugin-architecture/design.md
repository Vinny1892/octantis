## Context

Octantis is a pre-0.0.1 OTLP-native incident investigator. Today every component (ingesters, parser, MCP client, trigger filter, fingerprint cooldown, investigator, notifiers, metrics) is directly imported and wired in `main.py`. There are no extension points, no tier enforcement, and no way to ship a proprietary plugin without forking the repo. (Note: Octantis uses **"Ingester"** for its event-source Protocol. This is distinct from the OpenTelemetry Collector's "receiver" pipeline stage — Octantis Ingesters are plugins inside the Octantis process that produce `Event` instances for investigation, regardless of wire protocol.)

The Business Model requires an open-core split: an AGPL-3.0 core to protect against SaaS competitors, and a small Apache-2.0 SDK so third parties (and the future paid Octantis Cloud) can ship plugins without copyleft. Tech Spec 005 formalises the architecture — 6 Protocols (Ingester, Storage, MCPConnector, Processor, Notifier, UIProvider), entry-point discovery, JWT Ed25519 plan gating, dual standalone/distributed runtime via Redpanda, and a full license migration. Tech Spec 003 already introduced the MCP slot model and polymorphic resources this change builds on.

Constraints: (1) pre-0.0.1 with zero external users, so breaking changes are free now and expensive in one release; (2) every phase in TS 005 §11 mandates explicit test and documentation review as a ship gate; (3) standalone mode must keep zero external deps — Redpanda is opt-in via `OCTANTIS_MODE`; (4) the SDK surface, once published to PyPI, becomes a frozen contract with plugin authors.

Stakeholders: Vinicius (owner/operator), future plugin authors, future paying customers (pro/enterprise), self-hosted operators who stay on the free tier.

## Goals / Non-Goals

**Goals:**
- Ship a stable, minimal SDK surface (6 Protocols + shared types) that third parties can depend on.
- Make `main.py` a thin runtime dispatcher that does no component wiring — all components arrive via the Plugin Registry.
- Enforce tier limits (free/pro/enterprise) at registry load time with operator-friendly error messages.
- Support two deployment topologies from a single binary, chosen by env var, with identical observable behavior.
- Relicense core to AGPL-3.0 cleanly — LICENSE, headers, metadata, dependency audit, dual-license documentation.
- Treat test-suite review and documentation review as **first-class ship gates per phase**, not as post-launch cleanup.

**Non-Goals:**
- Plugin sandboxing (CPU/mem limits per plugin) — revisit if a third-party plugin misbehaves.
- Hot reload of plugins without restart — not worth the complexity pre-scale.
- A plugin marketplace UI — PyPI discovery is enough for Q2–Q4 2026; curated marketplace is 2027 roadmap.
- License revocation endpoint / call-home — offline JWT is sufficient until the first paying customer.
- Multi-region Redpanda / geo-replication — enterprise concern, not launch scope.
- Replacing Redpanda with NATS — captured as a future option; not dual-shipped.
- Back-compat shims: there are no external users, so the refactor is done in one cut, no feature flags.

## Decisions

### D1. Separate Apache-2.0 SDK package (`octantis-plugin-sdk`) distinct from the AGPL-3.0 core
The SDK contains only the 6 Protocols and shared dataclasses — no runtime code. Plugin authors depend on the SDK and are never linked to AGPL code at import time, which keeps their plugins free of copyleft obligations. This is the Grafana model (Apache-2.0 SDK, AGPL-3.0 core) and the clearest legal boundary available.
- **Alternative rejected:** single package with a "public API" subpackage. Harder to reason about legally; plugin authors would still `import octantis` transitively.
- **Trade-off:** two packages to version and release. Mitigated by keeping the SDK tiny and changing it rarely.

### D2. Python entry points (not a config file, not a registry service) for plugin discovery
Entry points are the Python packaging standard, work with `pip install`, and require zero bespoke loader code. The 6 groups — `octantis.ingesters`, `octantis.storage`, `octantis.mcp`, `octantis.processors`, `octantis.notifiers`, `octantis.ui` — are the contract with plugin authors. Once published, group names are frozen forever.
- **Alternative rejected:** YAML/TOML plugin manifest. Duplicates what `pyproject.toml` already expresses and adds a second source of truth.
- **Alternative rejected:** dynamic import from a config path. No discoverability via `pip list`, harder for operators.

### D3. Fixed load order by type: Ingesters → Storage → MCP → Processors → Notifiers → UI
Plugins with `setup()` side effects (opening connections, allocating resources) can otherwise race. Fixing the order costs a single sorted-by-type pass and is the same pattern Grafana and Ansible use. Processor ordering within the Processor type is by a configurable integer `priority` (TriggerFilter=100, Cooldown=200).
- **Alternative rejected:** topological sort on declared dependencies. More expressive, but no current plugin needs it, and it adds failure modes (cycles, missing deps).

### D4. JWT Ed25519 for license validation (offline-verifiable)
Asymmetric crypto lets the public key live safely in open-source code while only Anthropic (the issuer) holds the private key. Verification is ~50µs, works fully offline, and cannot be forged by reading the repo. Keys rotate by shipping a new public key in a core release.
- **Alternative rejected:** HMAC. Symmetric key in OSS means the "secret" is public — zero security.
- **Alternative rejected:** online license server. Requires operators to have egress to our infra; breaks air-gapped deployments.
- **Trade-off:** no revocation until we add a call-home. Acceptable pre-first-paying-customer.

### D5. `OCTANTIS_MODE` dispatch (`standalone` | `ingester` | `worker`) from one binary
Standalone uses `asyncio.TaskGroup` + semaphore (default 20 workers) with zero external deps. Distributed uses Redpanda: ingester publishes events, worker consumes with idempotent redelivery (message not ACKed until workflow completes). Same binary, same plugins, same Protocols — the mode only changes the runner.
- **Alternative rejected:** separate ingester/worker binaries. Doubles the release surface and makes local dev harder.
- **Alternative rejected:** NATS instead of Redpanda. Lighter (32MB vs 512MB) but weaker ecosystem and no Kafka compatibility for customer integration. Captured as a future plugin option.

### D6. Refactor all built-in components in one cut, no feature flags
Pre-0.0.1 with zero users. Feature flags would be dead code the day they ship. A clean cut is smaller to review and easier to reason about than a months-long parallel-implementation period.
- **Trade-off:** the refactor PR(s) will be large. Mitigated by phase-by-phase rollout (registry first, then each component family) and by the mandatory per-phase test/docs review gate.

### D7. AGPL-3.0 for core, Apache-2.0 for SDK — migrated atomically in Phase 6
Relicensing is one commit: `LICENSE`, per-file headers, `pyproject.toml` classifier, Helm `Chart.yaml`, README badges, and a new `LICENSING.md` that explains the dual model.
- **Rationale:** AGPL protects against SaaS competitors reselling Octantis. Apache-2.0 SDK keeps the plugin ecosystem unblocked. Grafana built a $6B+ business on this exact split.

### D8. Test and documentation review are phase-level ship gates, not follow-ups
Tech Spec 005 §11 already codifies this. The implementation enforces it two ways: (a) each phase in `tasks.md` has explicit "review tests" and "review docs" subtasks that must be checked off before the phase closes; (b) CI blocks merges if coverage drops below 94%. Reviewing tests means re-reading them against the new Protocol boundaries — not just "make green".

### D9. Worker idempotency via "don't ACK until done", not via dedup store
A worker that dies mid-investigation leaves the Redpanda message unacked, and the consumer group redelivers it to another worker. Workflows are written to be safe to run from scratch on the same event. This is simpler than a Redis/Postgres dedup table and sufficient for launch scale.
- **Trade-off:** duplicate notifications on crash near the end of a workflow. Documented; mitigated by notifiers carrying an event_id for operator-side dedup.

## Risks / Trade-offs

- **[Risk] SDK surface freezes too early and we need to break it.** → Mitigate by keeping the SDK minimal (Protocols + dataclasses, no helpers) and by documenting a deprecation policy (one minor release of warnings before removal). Pre-0.0.1 SDK can still break; we'll declare API stability at 1.0.
- **[Risk] Large refactor PR regresses existing behavior despite tests passing.** → Mitigate by reviewing each existing test against the new Protocol boundary (D8) rather than just running `pytest`; by staging the refactor one component family per phase; and by manually exercising end-to-end flows (standalone + distributed) before each phase closes.
- **[Risk] AGPL scares off potential users or contributors.** → Mitigate with a clear `LICENSING.md` FAQ that explains: AGPL triggers only when you *distribute or offer as a network service*; internal self-hosted use is unaffected; plugins stay Apache-2.0.
- **[Risk] JWT private key leak → anyone can mint licenses.** → Mitigate with a documented rotation procedure (ship a new public key in a patch release), keep the private key offline (hardware-backed or in a sealed secrets store), and log failed verifications so abuse is visible.
- **[Risk] Redpanda adds a hard dependency that complicates operations.** → Mitigate by keeping standalone mode fully zero-dep and defaulting to it; Redpanda is only required when `OCTANTIS_MODE` is set to `ingester` or `worker`. Helm chart makes Redpanda an optional subchart.
- **[Risk] Phase 2 (refactoring all built-ins) is too large to review in one PR.** → Mitigate by splitting Phase 2 into sub-PRs by component family (ingesters, MCP, processors, notifiers, metrics), each independently test-reviewed and docs-reviewed.
- **[Trade-off] Fixed load order and fixed entry-point group names limit future flexibility.** → Accepted: the cost of changing them after publishing is breaking every installed plugin. Lock them once, document them loudly.
- **[Trade-off] Per-phase mandatory docs review slows delivery.** → Accepted: docs drift is the primary failure mode of plugin ecosystems (Tech Spec 005 §11 explicitly calls this out). Slower phases, fewer dead docs.

## Migration Plan

Rollout follows the 6 phases defined in Tech Spec 005 §11. Each phase is independent, independently rollback-able, and gated by its own test + docs review.

1. **Phase 1 — SDK + Registry + Protocols.** Publish `octantis-plugin-sdk` to PyPI. Land the Plugin Registry with entry-point discovery. Define all 5 Protocols. Validate: one built-in plugin loads via entry point; registry unit tests pass. Rollback: `git revert`; no external consumers yet.
2. **Phase 2 — Built-in refactoring.** Refactor every existing component to implement its Protocol and register via entry point in `pyproject.toml`. Remove direct imports from `main.py`. Validate: all 254 existing tests pass *after being reviewed against Protocol boundaries*; end-to-end behavior identical. Rollback: `git revert`; pre-0.0.1, no users.
3. **Phase 3 — Plan gating.** JWT Ed25519 validator + `PlanGatingEngine` with free/pro/enterprise rules and MCP slot enforcement. Validate: start with 2 MCPs + no license → clear error; start with pro JWT → loads 2 MCPs. Rollback: remove `PlanGatingEngine`, hardcode free-tier limits.
4. **Phase 4 — Concurrent standalone.** `asyncio.TaskGroup` + semaphore runner in standalone mode. Validate: 5 events → 5 parallel investigations (logs/metrics). Rollback: revert to sequential `await`.
5. **Phase 5 — Distributed mode.** Redpanda client; `OCTANTIS_MODE=ingester` publishes; `OCTANTIS_MODE=worker` consumes. Validate: ingester + 3 workers + Redpanda container, events distributed, worker crash → redelivery. Rollback: set `OCTANTIS_MODE=standalone`; Redpanda deployment untouched.
6. **Phase 6 — License migration.** AGPL-3.0 `LICENSE` + headers + `pyproject.toml` + Helm `Chart.yaml` + README + `LICENSING.md`. Validate: `LICENSE` is AGPL-3.0, SPDX headers present in all source files. Rollback: `git revert` on LICENSE + headers.

**Per-phase gate (mandatory, applies to all 6 phases):**
- [ ] Test suite reviewed against the new Protocol / runtime boundary — not just "made green".
- [ ] Coverage ≥ 94% in CI.
- [ ] All affected docs updated in the same PR (README, AGENTS.md, LICENSING.md, SDK reference, operator guides, PRD/Tech Spec cross-refs, FAQ).

A phase that fails its gate does not ship — it is reverted and redone, not patched forward.

## Open Questions

- **Kafka client library:** `aiokafka` (pure Python, easier install) vs `confluent-kafka` (librdkafka, faster, heavier deps). Decide before Phase 5. Leaning `aiokafka` for the simpler dependency story.
- **Where does the JWT public key live?** Hardcoded in `src/octantis/licensing/` vs fetched from a known URL at build time. Hardcoded is simpler and air-gap-friendly; confirm before Phase 3.
- **Plugin metadata schema in `pyproject.toml`:** do we require a `[tool.octantis.plugin]` table with `name`, `version`, `tier`, or infer everything from the entry point? Decide before SDK 1.0.
- **CI enforcement of "tests were reviewed":** resolved — PR template checklist item "Tests reviewed against Protocol boundaries (not just 'make green')". Human judgment enforced via checklist, not automation.
- **Redpanda minimum version / schema-registry usage:** do we use Redpanda's built-in schema registry now, or keep event payloads as opaque JSON for launch? Leaning opaque JSON for launch, adopt schema registry when a plugin author needs it.
