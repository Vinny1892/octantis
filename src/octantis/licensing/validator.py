"""JWT Ed25519 license validator — fully offline, no network calls.

The public key lives at src/octantis/licensing/public_key.pem and is shipped
with the binary. Only Octantis (the issuer) holds the private key.

Usage:
    from octantis.licensing.validator import validate_license_jwt
    tier = validate_license_jwt(token)   # returns PluginTier
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import jwt
import structlog
from octantis_plugin_sdk import PluginTier

log = structlog.get_logger(__name__)

_ISSUER = "octantis"
_ALGORITHM = "EdDSA"

# Load the public key once at import time (PEM bytes only — no private key here).
_PUBLIC_KEY_PEM: bytes = (
    files("octantis.licensing").joinpath("public_key.pem").read_bytes()
)


class LicenseValidationError(ValueError):
    """Raised when the license JWT cannot be validated."""


def validate_license_jwt(token: str) -> PluginTier:
    """Verify a signed JWT and return the plan tier.

    Verifies:
    - Ed25519 signature against the bundled public key
    - `iss` claim must be "octantis"
    - `exp` and `iat` claims must be present and within validity window

    Returns PluginTier enum value on success.
    Raises LicenseValidationError on any failure.
    """
    try:
        payload = jwt.decode(
            token,
            _PUBLIC_KEY_PEM,
            algorithms=[_ALGORITHM],
            options={"require": ["iss", "exp", "iat", "tier"]},
            issuer=_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise LicenseValidationError("license JWT has expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise LicenseValidationError(f"unknown issuer in license JWT: {exc}") from exc
    except jwt.InvalidSignatureError as exc:
        raise LicenseValidationError("license JWT signature is invalid") from exc
    except jwt.DecodeError as exc:
        raise LicenseValidationError(f"license JWT is malformed: {exc}") from exc
    except jwt.PyJWTError as exc:
        raise LicenseValidationError(f"license JWT validation failed: {exc}") from exc

    raw_tier = payload.get("tier", "").lower()
    try:
        return PluginTier(raw_tier)
    except ValueError:
        raise LicenseValidationError(
            f"unknown tier in license JWT: {raw_tier!r}. "
            f"Expected one of: {[t.value for t in PluginTier]}"
        )


def resolve_tier() -> PluginTier:
    """Determine the active plan tier from the environment.

    Reads `OCTANTIS_LICENSE_JWT`. If missing → free tier (no error).
    If present but invalid → logs error and falls back to free tier.
    """
    token = os.environ.get("OCTANTIS_LICENSE_JWT", "").strip()
    if not token:
        log.info("octantis.license.free_tier", reason="no_jwt_configured")
        return PluginTier.FREE

    try:
        tier = validate_license_jwt(token)
        log.info("octantis.license.validated", tier=tier.value)
        return tier
    except LicenseValidationError as exc:
        log.error(
            "octantis.license.invalid",
            error=str(exc),
            remediation="Check OCTANTIS_LICENSE_JWT or contact support@octantis.dev",
        )
        log.warning("octantis.license.fallback_free_tier")
        return PluginTier.FREE
