"""Plugin registry tests — discovery, load order, duplicates, lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from octantis.plugins.registry import (
    DuplicatePluginError,
    PluginLoadError,
    PluginRegistry,
    PluginType,
)

# ---- plugin test doubles ----------------------------------------------------

class FakeIngester:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def setup(self, config: dict[str, Any]) -> None:
        self.calls.append("setup")

    def teardown(self) -> None:
        self.calls.append("teardown")

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def events(self):
        if False:
            yield None


class FakeStorage:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def setup(self, config: dict[str, Any]) -> None:
        self.calls.append("setup")

    def teardown(self) -> None:
        self.calls.append("teardown")

    async def save_investigation(self, investigation, analysis, plan) -> str:
        return "id-1"

    async def is_cooled_down(self, fingerprint: str) -> bool:
        return False


class FakeMCP:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    def get_tools(self) -> list[Any]:
        return []
    def is_degraded(self) -> bool:
        return False


class FakeProcessorHigh:
    priority = 200
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def process(self, event):
        return event


class FakeProcessorLow:
    priority = 100
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def process(self, event):
        return event


class FakeNotifier:
    def setup(self, config: dict[str, Any]) -> None: ...
    def teardown(self) -> None: ...
    async def send(self, result) -> None: ...


class SetupRaises:
    def setup(self, config: dict[str, Any]) -> None:
        raise RuntimeError("boom")
    def teardown(self) -> None: ...
    async def send(self, result) -> None: ...


class TeardownRaises:
    def __init__(self) -> None:
        self.setup_called = False
    def setup(self, config: dict[str, Any]) -> None:
        self.setup_called = True
    def teardown(self) -> None:
        raise RuntimeError("teardown boom")
    async def send(self, result) -> None: ...


class NotAProtocol:
    """Missing required methods — must fail conformance."""
    pass


# ---- entry-point fake helpers ----------------------------------------------

@dataclass
class _FakeDist:
    name: str
    version: str


@dataclass
class _FakeEP:
    name: str
    cls: type
    dist_name: str = "test-pkg"
    dist_version: str = "9.9.9"

    def load(self):
        return self.cls

    @property
    def dist(self):
        return _FakeDist(name=self.dist_name, version=self.dist_version)


def _patch_entry_points(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, list[_FakeEP]]) -> None:
    """Patch importlib.metadata.entry_points used by the registry module."""

    def fake(*, group: str):
        return mapping.get(group, [])

    monkeypatch.setattr("octantis.plugins.registry.entry_points", fake)


# ---- tests -----------------------------------------------------------------

def test_discovers_plugin_from_entry_point(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.ingesters": [_FakeEP("otlp-grpc", FakeIngester)],
    })
    reg = PluginRegistry()
    loaded = reg.discover()
    assert len(loaded) == 1
    assert loaded[0].name == "otlp-grpc"
    assert loaded[0].type is PluginType.INGESTER
    assert loaded[0].source_package == "test-pkg"
    assert loaded[0].version == "9.9.9"


def test_load_order_storage_before_mcp_before_processor(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.processors": [_FakeEP("proc", FakeProcessorLow)],
        "octantis.mcp": [_FakeEP("mcp", FakeMCP)],
        "octantis.ingesters": [_FakeEP("recv", FakeIngester)],
    })
    reg = PluginRegistry()
    loaded = reg.discover()
    types = [p.type for p in loaded]
    assert types == [PluginType.INGESTER, PluginType.MCP, PluginType.PROCESSOR]


def test_processors_sorted_by_priority_ascending(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.processors": [
            _FakeEP("high", FakeProcessorHigh),  # priority 200
            _FakeEP("low", FakeProcessorLow),    # priority 100
        ],
    })
    reg = PluginRegistry()
    loaded = reg.discover()
    names = [p.name for p in loaded]
    assert names == ["low", "high"]


def test_duplicate_name_in_same_group_raises(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [
            _FakeEP("slack", FakeNotifier, dist_name="pkg-a"),
            _FakeEP("slack", FakeNotifier, dist_name="pkg-b"),
        ],
    })
    reg = PluginRegistry()
    with pytest.raises(DuplicatePluginError) as exc:
        reg.discover()
    msg = str(exc.value)
    assert "slack" in msg
    assert "pkg-a" in msg and "pkg-b" in msg


def test_same_name_across_groups_is_allowed(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.ingesters": [_FakeEP("alpha", FakeIngester)],
        "octantis.notifiers": [_FakeEP("alpha", FakeNotifier)],
    })
    reg = PluginRegistry()
    loaded = reg.discover()
    assert {p.name for p in loaded} == {"alpha"}
    assert {p.type for p in loaded} == {PluginType.INGESTER, PluginType.NOTIFIER}


def test_non_conforming_plugin_rejected(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [_FakeEP("bad", NotAProtocol)],
    })
    reg = PluginRegistry()
    with pytest.raises(PluginLoadError) as exc:
        reg.discover()
    assert "Notifier" in str(exc.value)


def test_setup_called_in_load_order(monkeypatch):
    order: list[str] = []

    class R:
        def setup(self, c): order.append("R")
        def teardown(self): ...
        async def start(self): ...
        async def stop(self): ...
        async def events(self):
            if False:
                yield None

    class M:
        def setup(self, c): order.append("M")
        def teardown(self): ...
        def get_tools(self): return []
        def is_degraded(self): return False

    class N:
        def setup(self, c): order.append("N")
        def teardown(self): ...
        async def send(self, r): ...

    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [_FakeEP("n", N)],
        "octantis.ingesters": [_FakeEP("r", R)],
        "octantis.mcp": [_FakeEP("m", M)],
    })
    reg = PluginRegistry()
    reg.discover()
    reg.setup_all()
    assert order == ["R", "M", "N"]


def test_teardown_in_reverse_load_order(monkeypatch):
    order: list[str] = []

    class R:
        def setup(self, c): ...
        def teardown(self): order.append("R")
        async def start(self): ...
        async def stop(self): ...
        async def events(self):
            if False:
                yield None

    class M:
        def setup(self, c): ...
        def teardown(self): order.append("M")
        def get_tools(self): return []
        def is_degraded(self): return False

    class N:
        def setup(self, c): ...
        def teardown(self): order.append("N")
        async def send(self, r): ...

    _patch_entry_points(monkeypatch, {
        "octantis.ingesters": [_FakeEP("r", R)],
        "octantis.mcp": [_FakeEP("m", M)],
        "octantis.notifiers": [_FakeEP("n", N)],
    })
    reg = PluginRegistry()
    reg.discover()
    reg.setup_all()
    reg.teardown_all()
    assert order == ["N", "M", "R"]


def test_teardown_continues_after_exception(monkeypatch):
    """A teardown raising must not stop the others."""
    survivors: list[str] = []

    class Good:
        def setup(self, c): ...
        def teardown(self): survivors.append("good")
        async def send(self, r): ...

    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [
            _FakeEP("raises", TeardownRaises),
            _FakeEP("good", Good),
        ],
    })
    reg = PluginRegistry()
    reg.discover()
    reg.setup_all()
    reg.teardown_all()  # must not raise
    assert survivors == ["good"]


def test_setup_failure_propagates(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [_FakeEP("bad", SetupRaises)],
    })
    reg = PluginRegistry()
    reg.discover()
    with pytest.raises(RuntimeError, match="boom"):
        reg.setup_all()


def test_plugins_filter_by_type(monkeypatch):
    _patch_entry_points(monkeypatch, {
        "octantis.ingesters": [_FakeEP("r", FakeIngester)],
        "octantis.notifiers": [_FakeEP("n", FakeNotifier)],
    })
    reg = PluginRegistry()
    reg.discover()
    assert [p.name for p in reg.plugins(PluginType.INGESTER)] == ["r"]
    assert [p.name for p in reg.plugins(PluginType.NOTIFIER)] == ["n"]
    assert [p.name for p in reg.plugins()] == ["r", "n"]


def test_setup_passes_per_plugin_config(monkeypatch):
    received: dict[str, dict] = {}

    class N:
        def setup(self, c): received["n"] = c
        def teardown(self): ...
        async def send(self, r): ...

    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [_FakeEP("n", N)],
    })
    reg = PluginRegistry()
    reg.discover()
    reg.setup_all({"n": {"webhook_url": "https://example.com"}})
    assert received["n"] == {"webhook_url": "https://example.com"}


def test_lifecycle_logs_emitted(monkeypatch, capsys):
    _patch_entry_points(monkeypatch, {
        "octantis.notifiers": [_FakeEP("log-test", FakeNotifier)],
    })
    reg = PluginRegistry()
    reg.discover()
    reg.setup_all()
    reg.teardown_all()
    out = capsys.readouterr().out
    for expected in (
        "plugin.loaded",
        "plugin.registry.discovered",
        "plugin.setup_started",
        "plugin.setup_completed",
        "plugin.teardown_started",
        "plugin.teardown_completed",
    ):
        assert expected in out, f"missing lifecycle event {expected!r}"
