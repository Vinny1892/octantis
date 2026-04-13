# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plugin subsystem — discovery, loading, lifecycle."""

from .registry import (
    DuplicatePluginError,
    LoadedPlugin,
    PluginLoadError,
    PluginRegistry,
    PluginType,
)

__all__ = [
    "DuplicatePluginError",
    "LoadedPlugin",
    "PluginLoadError",
    "PluginRegistry",
    "PluginType",
]
