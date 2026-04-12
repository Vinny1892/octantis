"""LLM severity analysis model.

Canonical definitions live in `octantis_plugin_sdk` (Apache-2.0 stable
contract). Core re-exports them so internal imports keep working.
"""

from octantis_plugin_sdk import Severity, SeverityAnalysis

__all__ = ["Severity", "SeverityAnalysis"]
