# SPDX-License-Identifier: Apache-2.0
"""The six Octantis plugin Protocols.

Plugins implement one of these Protocols and register under the matching
entry-point group. The Protocols are `runtime_checkable` so core can validate
conformance before invoking a plugin.

Lifecycle:
    1. Plugin class is discovered via entry point and instantiated with no args.
    2. Registry calls `setup(config)` in the fixed load order.
    3. Runtime invokes Protocol-specific methods as events flow.
    4. On shutdown, registry calls `teardown()` in reverse load order.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .action_plan import ActionPlan
from .analysis import SeverityAnalysis
from .types import Event, InvestigationResult, Tool


@runtime_checkable
class Ingester(Protocol):
    """Event source. Ingests events from an external system and delivers them
    to the Octantis pipeline.

    Named `Ingester` — distinct from the OpenTelemetry Collector's "receiver"
    pipeline stage — to avoid confusion: the Octantis Ingester runs inside the
    Octantis process and emits SDK `Event` instances to the processor chain.

    Examples: OTLP gRPC ingester, OTLP HTTP ingester, log tailer, alert webhook,
    Kafka consumer.
    """

    def setup(self, config: dict[str, Any]) -> None: ...

    def teardown(self) -> None: ...

    async def start(self) -> None:
        """Start receiving events (bind ports, connect to brokers, etc.)."""
        ...

    async def stop(self) -> None:
        """Gracefully stop receiving events."""
        ...

    async def events(self) -> Any:
        """Async iterator yielding `Event` instances. Implementations may be
        async generators or objects exposing `__aiter__`."""
        ...


@runtime_checkable
class Storage(Protocol):
    """Persistent storage backend. Persists investigation records, cooldown
    state, and other durable data.

    Examples: MemoryStorage (in-memory dict), PostgresStorage, RedisStorage.
    """

    def setup(self, config: dict[str, Any]) -> None: ...

    def teardown(self) -> None: ...

    async def save_investigation(
        self,
        investigation: InvestigationResult,
        analysis: SeverityAnalysis,
        plan: ActionPlan | None,
    ) -> str:
        """Persist an investigation. Returns record ID."""
        ...

    async def is_cooled_down(self, fingerprint: str) -> bool:
        """Check if a fingerprint is in cooldown."""
        ...


@runtime_checkable
class MCPConnector(Protocol):
    """MCP tool provider. Exposes callable tools the investigation loop may use.

    Examples: Grafana MCP (PromQL/LogQL), Kubernetes MCP, Docker MCP, AWS MCP.
    """

    def setup(self, config: dict[str, Any]) -> None: ...

    def teardown(self) -> None: ...

    def get_tools(self) -> list[Tool]: ...

    def is_degraded(self) -> bool: ...


@runtime_checkable
class Processor(Protocol):
    """Event-pipeline stage. Transforms, filters, or enriches an event.

    Processors are ordered by a `priority` integer (lower runs first).
    Returning `None` drops the event from the pipeline.
    """

    priority: int

    def setup(self, config: dict[str, Any]) -> None: ...

    def teardown(self) -> None: ...

    async def process(self, event: Event) -> Event | None: ...


@runtime_checkable
class Notifier(Protocol):
    """Outbound destination. Delivers an `InvestigationResult` plus the LLM
    classification (`SeverityAnalysis`) and optional remediation plan
    (`ActionPlan`) to an external system (chat, email, webhook, ...).

    `extra_text` is a free-form appendix (for example, degradation warnings)
    added by the runtime after analysis and plan have been produced.
    """

    def setup(self, config: dict[str, Any]) -> None: ...

    def teardown(self) -> None: ...

    async def send(
        self,
        result: InvestigationResult,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
        extra_text: str = "",
    ) -> None: ...


@runtime_checkable
class UIProvider(Protocol):
    """UI surface. Enterprise-tier only. Exposes HTTP routes or a web app.

    The runtime mounts the provider's ASGI app under the configured prefix.
    """

    def setup(self, config: dict[str, Any]) -> None: ...

    def teardown(self) -> None: ...

    def asgi_app(self) -> Any: ...
