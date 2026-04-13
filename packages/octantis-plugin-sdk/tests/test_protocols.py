# SPDX-License-Identifier: Apache-2.0
"""Protocol conformance tests — the SDK's contract with plugin authors."""

from __future__ import annotations

from typing import Any

from octantis_plugin_sdk import (
    ActionPlan,
    Event,
    InvestigationResult,
    MCPConnector,
    Notifier,
    Processor,
    Ingester,
    SeverityAnalysis,
    Storage,
    Tool,
    UIProvider,
)


class _ValidIngester:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def events(self) -> Any:
        yield Event(event_id="x", event_type="metric", source="t")


class _ValidStorage:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def save_investigation(
        self,
        investigation: InvestigationResult,
        analysis: SeverityAnalysis,
        plan: ActionPlan | None,
    ) -> str:
        return "id-1"
    async def is_cooled_down(self, fingerprint: str) -> bool:
        return False


class _ValidMCP:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    def get_tools(self) -> list[Tool]:
        return []
    def is_degraded(self) -> bool:
        return False


class _ValidProcessor:
    priority = 100
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def process(self, event: Event) -> Event | None:
        return event


class _ValidNotifier:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def send(
        self,
        result: InvestigationResult,
        analysis: SeverityAnalysis,
        action_plan: ActionPlan | None = None,
        extra_text: str = "",
    ) -> None: ...


class _ValidUI:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    def asgi_app(self) -> Any:
        return object()


class _MissingSetup:
    def teardown(self) -> None: ...


def test_ingester_protocol_conformance():
    assert isinstance(_ValidIngester(), Ingester)


def test_storage_protocol_conformance():
    assert isinstance(_ValidStorage(), Storage)


def test_mcp_protocol_conformance():
    assert isinstance(_ValidMCP(), MCPConnector)


def test_processor_protocol_conformance():
    assert isinstance(_ValidProcessor(), Processor)


def test_notifier_protocol_conformance():
    assert isinstance(_ValidNotifier(), Notifier)


def test_ui_protocol_conformance():
    assert isinstance(_ValidUI(), UIProvider)


def test_missing_methods_fails_conformance():
    assert not isinstance(_MissingSetup(), Notifier)


def test_ingester_not_accidentally_notifier():
    assert not isinstance(_ValidIngester(), Notifier)
    assert not isinstance(_ValidNotifier(), Ingester)


def test_storage_not_accidentally_ingester():
    assert not isinstance(_ValidStorage(), Ingester)
    assert not isinstance(_ValidIngester(), Storage)
