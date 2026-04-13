# SPDX-License-Identifier: AGPL-3.0-or-later
"""PlanGatingEngine — enforces plugin limits per tier.

Tier rules (from Tech Spec 005):
  free:       1 MCP connector, 1 notifier, 0 UI providers
  pro:        3 MCP connectors, 3 notifiers, 0 UI providers
  enterprise: unlimited MCP, unlimited notifiers, 1 UI provider

Gating runs between registry discovery and plugin setup() so that no
external connections are made before tier enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from octantis_plugin_sdk import PluginTier

if TYPE_CHECKING:
    from octantis.plugins.registry import LoadedPlugin

log = structlog.get_logger(__name__)

_UNLIMITED = 999_999


@dataclass(frozen=True)
class _TierLimits:
    mcp: int
    notifiers: int
    ui: int


_LIMITS: dict[PluginTier, _TierLimits] = {
    PluginTier.FREE: _TierLimits(mcp=1, notifiers=1, ui=0),
    PluginTier.PRO: _TierLimits(mcp=3, notifiers=3, ui=0),
    PluginTier.ENTERPRISE: _TierLimits(mcp=_UNLIMITED, notifiers=_UNLIMITED, ui=1),
}


class GatingViolationError(RuntimeError):
    """Raised when a plugin load violates the active plan tier."""


@dataclass
class PlanGatingEngine:
    """Enforces per-tier plugin count limits.

    Call `enforce(plugins)` with the list from `registry.discover()`.
    Raises `GatingViolationError` on the first violation.
    """

    tier: PluginTier

    def enforce(self, plugins: list[LoadedPlugin]) -> None:
        """Validate that `plugins` respect the tier limits.

        Raises GatingViolationError with a remediation message on violation.
        Emits structured log entries for all violations found.
        """
        from octantis.plugins.registry import PluginType

        limits = _LIMITS[self.tier]
        violations: list[str] = []

        mcp_plugins = [p for p in plugins if p.type is PluginType.MCP]
        notifier_plugins = [p for p in plugins if p.type is PluginType.NOTIFIER]
        ui_plugins = [p for p in plugins if p.type is PluginType.UI]

        def _check(label: str, installed: list[LoadedPlugin], limit: int) -> None:
            count = len(installed)
            if count > limit:
                names = [p.name for p in installed]
                msg = (
                    f"{label}: {count} installed but tier={self.tier.value!r} "
                    f"allows {limit}. Installed: {names}. "
                    f"Upgrade to a higher tier or remove {count - limit} plugin(s)."
                )
                log.error(
                    "octantis.gating.violation",
                    plugin_type=label,
                    tier=self.tier.value,
                    limit=limit,
                    installed_count=count,
                    plugin_names=names,
                    remediation=f"Remove {count - limit} {label} plugin(s) or upgrade plan.",
                )
                violations.append(msg)

        _check("mcp", mcp_plugins, limits.mcp)
        _check("notifiers", notifier_plugins, limits.notifiers)
        _check("ui", ui_plugins, limits.ui)

        if violations:
            raise GatingViolationError(
                f"Plan gating blocked {len(violations)} plugin type(s) "
                f"for tier={self.tier.value!r}:\n" + "\n".join(violations)
            )

        log.info(
            "octantis.gating.passed",
            tier=self.tier.value,
            mcp_count=len(mcp_plugins),
            notifier_count=len(notifier_plugins),
            ui_count=len(ui_plugins),
        )
