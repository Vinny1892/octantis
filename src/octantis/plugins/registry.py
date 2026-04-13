# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plugin registry — entry-point discovery, fixed load order, lifecycle logging.

Contract with plugin authors lives in `octantis_plugin_sdk`. The registry
itself is core runtime and is AGPL-3.0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from importlib.metadata import EntryPoint, entry_points
from typing import Any

import structlog
from octantis_plugin_sdk import Ingester, MCPConnector, Notifier, Processor, Storage, UIProvider

logger = structlog.get_logger(__name__)


class PluginType(str, Enum):
    """The six plugin types, declared in the fixed load order."""

    INGESTER = "ingesters"
    STORAGE = "storage"
    MCP = "mcp"
    PROCESSOR = "processors"
    NOTIFIER = "notifiers"
    UI = "ui"


_LOAD_ORDER: tuple[PluginType, ...] = (
    PluginType.INGESTER,
    PluginType.STORAGE,
    PluginType.MCP,
    PluginType.PROCESSOR,
    PluginType.NOTIFIER,
    PluginType.UI,
)

_ENTRY_POINT_GROUP: dict[PluginType, str] = {
    PluginType.INGESTER: "octantis.ingesters",
    PluginType.STORAGE: "octantis.storage",
    PluginType.MCP: "octantis.mcp",
    PluginType.PROCESSOR: "octantis.processors",
    PluginType.NOTIFIER: "octantis.notifiers",
    PluginType.UI: "octantis.ui",
}

_PROTOCOL_BY_TYPE: dict[PluginType, type] = {
    PluginType.INGESTER: Ingester,
    PluginType.STORAGE: Storage,
    PluginType.MCP: MCPConnector,
    PluginType.PROCESSOR: Processor,
    PluginType.NOTIFIER: Notifier,
    PluginType.UI: UIProvider,
}


class PluginLoadError(RuntimeError):
    """Raised when a plugin cannot be instantiated or fails conformance check."""


class DuplicatePluginError(RuntimeError):
    """Raised when two plugins register the same name in the same group."""


@dataclass
class LoadedPlugin:
    """A plugin that has been instantiated and is ready for setup()."""

    name: str
    type: PluginType
    instance: Any
    source_package: str
    version: str
    priority: int = 0  # only meaningful for PluginType.PROCESSOR

    def __repr__(self) -> str:  # pragma: no cover — trivial
        return f"LoadedPlugin(name={self.name!r}, type={self.type.value}, pkg={self.source_package})"


@dataclass
class PluginRegistry:
    """Discovers plugins via entry points and drives their lifecycle."""

    _plugins: list[LoadedPlugin] = field(default_factory=list)
    _setup_done: list[LoadedPlugin] = field(default_factory=list)

    def discover(self) -> list[LoadedPlugin]:
        """Load all plugins from entry points in the fixed type order.

        Within each type, order is insertion (discovery) order, except for
        processors which are sorted by their `priority` attribute ascending.

        Raises DuplicatePluginError if two plugins share a name within a type.
        Raises PluginLoadError if a plugin fails to instantiate or violates
        its Protocol.
        """
        self._plugins.clear()
        for ptype in _LOAD_ORDER:
            group = _ENTRY_POINT_GROUP[ptype]
            eps = list(entry_points(group=group))
            loaded_for_type: list[LoadedPlugin] = []
            seen_names: dict[str, str] = {}
            for ep in eps:
                if ep.name in seen_names:
                    raise DuplicatePluginError(
                        f"duplicate plugin name {ep.name!r} in group {group!r}: "
                        f"first from {seen_names[ep.name]}, second from {_ep_dist_name(ep)}"
                    )
                seen_names[ep.name] = _ep_dist_name(ep)
                loaded_for_type.append(self._load_one(ep, ptype))
            if ptype is PluginType.PROCESSOR:
                loaded_for_type.sort(key=lambda p: p.priority)
            self._plugins.extend(loaded_for_type)
        logger.info(
            "plugin.registry.discovered",
            total=len(self._plugins),
            by_type={t.value: sum(1 for p in self._plugins if p.type is t) for t in _LOAD_ORDER},
        )
        return list(self._plugins)

    def _load_one(self, ep: EntryPoint, ptype: PluginType) -> LoadedPlugin:
        source = _ep_dist_name(ep)
        try:
            cls = ep.load()
        except Exception as exc:
            raise PluginLoadError(
                f"failed to import plugin {ep.name!r} from {source}: {exc}"
            ) from exc
        try:
            instance = cls()
        except Exception as exc:
            raise PluginLoadError(
                f"failed to instantiate plugin {ep.name!r} from {source}: {exc}"
            ) from exc
        proto = _PROTOCOL_BY_TYPE[ptype]
        if not isinstance(instance, proto):
            raise PluginLoadError(
                f"plugin {ep.name!r} from {source} does not satisfy {proto.__name__} Protocol"
            )
        priority = int(getattr(instance, "priority", 0)) if ptype is PluginType.PROCESSOR else 0
        version = _ep_dist_version(ep)
        loaded = LoadedPlugin(
            name=ep.name,
            type=ptype,
            instance=instance,
            source_package=source,
            version=version,
            priority=priority,
        )
        logger.info(
            "plugin.loaded",
            plugin_name=loaded.name,
            plugin_type=ptype.value,
            plugin_version=version,
            source_package=source,
        )
        return loaded

    def gate(self, tier: Any) -> None:
        """Enforce plan tier limits on the discovered plugin list.

        Must be called after `discover()` and before `setup_all()`.
        Raises `GatingViolationError` if any plugin type exceeds the tier limit.
        """
        from octantis.licensing.gating import PlanGatingEngine

        engine = PlanGatingEngine(tier=tier)
        engine.enforce(self._plugins)

    def setup_all(self, config: dict[str, dict[str, Any]] | None = None) -> None:
        """Invoke setup() on every discovered plugin in load order.

        `config` is a mapping plugin-name -> per-plugin config dict. Plugins
        not present in the mapping receive an empty dict.
        """
        config = config or {}
        for plugin in self._plugins:
            per_plugin = config.get(plugin.name, {})
            logger.info(
                "plugin.setup_started",
                plugin_name=plugin.name,
                plugin_type=plugin.type.value,
                plugin_version=plugin.version,
                source_package=plugin.source_package,
            )
            t0 = time.perf_counter()
            try:
                plugin.instance.setup(per_plugin)
            except Exception as exc:
                logger.error(
                    "plugin.setup_failed",
                    plugin_name=plugin.name,
                    plugin_type=plugin.type.value,
                    source_package=plugin.source_package,
                    error=str(exc),
                )
                raise
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self._setup_done.append(plugin)
            logger.info(
                "plugin.setup_completed",
                plugin_name=plugin.name,
                plugin_type=plugin.type.value,
                plugin_version=plugin.version,
                source_package=plugin.source_package,
                duration_ms=round(duration_ms, 3),
            )

    def teardown_all(self) -> None:
        """Invoke teardown() in the reverse of load order. Exceptions are
        logged but do not prevent other plugins from tearing down."""
        for plugin in reversed(self._setup_done):
            logger.info(
                "plugin.teardown_started",
                plugin_name=plugin.name,
                plugin_type=plugin.type.value,
            )
            t0 = time.perf_counter()
            try:
                plugin.instance.teardown()
            except Exception as exc:
                logger.error(
                    "plugin.teardown_failed",
                    plugin_name=plugin.name,
                    plugin_type=plugin.type.value,
                    error=str(exc),
                )
                continue
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "plugin.teardown_completed",
                plugin_name=plugin.name,
                plugin_type=plugin.type.value,
                duration_ms=round(duration_ms, 3),
            )
        self._setup_done.clear()

    def plugins(self, ptype: PluginType | None = None) -> list[LoadedPlugin]:
        """Return loaded plugins, optionally filtered by type."""
        if ptype is None:
            return list(self._plugins)
        return [p for p in self._plugins if p.type is ptype]


def _ep_dist_name(ep: EntryPoint) -> str:
    dist = getattr(ep, "dist", None)
    if dist is not None:
        name = getattr(dist, "name", None) or getattr(getattr(dist, "metadata", None), "get", lambda _: None)("Name")
        if name:
            return str(name)
    return "unknown"


def _ep_dist_version(ep: EntryPoint) -> str:
    dist = getattr(ep, "dist", None)
    if dist is not None:
        version = getattr(dist, "version", None)
        if version:
            return str(version)
    return "0.0.0"
