# SPDX-License-Identifier: Apache-2.0
"""Octantis Plugin SDK — stable public contract for plugin authors."""

from .action_plan import ActionPlan, ActionStep, StepType
from .analysis import Severity, SeverityAnalysis
from .protocols import Ingester, MCPConnector, Notifier, Processor, Storage, UIProvider
from .types import (
    Event,
    InvestigationResult,
    PluginMetadata,
    PluginTier,
    Tool,
)

__version__ = "0.1.0"

__all__ = [
    "ActionPlan",
    "ActionStep",
    "Event",
    "Ingester",
    "InvestigationResult",
    "MCPConnector",
    "Notifier",
    "PluginMetadata",
    "PluginTier",
    "Processor",
    "Severity",
    "SeverityAnalysis",
    "StepType",
    "Storage",
    "Tool",
    "UIProvider",
    "__version__",
]
