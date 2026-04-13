"""Tests for JWT license validation and PlanGatingEngine."""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from octantis_plugin_sdk import PluginTier

from octantis.licensing.gating import GatingViolationError, PlanGatingEngine
from octantis.licensing.validator import LicenseValidationError, validate_license_jwt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def keypair():
    """Generate a fresh Ed25519 keypair for tests.  Never touches the on-disk key."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pub_pem = pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return priv_pem, pub_pem


def _make_token(priv_pem: bytes, tier: str = "free", *, expired: bool = False, bad_iss: bool = False) -> str:
    now = int(time.time())
    payload = {
        "iss": "octantis" if not bad_iss else "evil-corp",
        "iat": now - 10,
        "exp": (now - 5) if expired else (now + 3600),
        "tier": tier,
    }
    return jwt.encode(payload, priv_pem, algorithm="EdDSA")


def _patch_public_key(pub_pem: bytes):
    """Context manager that patches the bundled public key with a test key."""
    return patch("octantis.licensing.validator._PUBLIC_KEY_PEM", pub_pem)


# ---------------------------------------------------------------------------
# JWT validator tests
# ---------------------------------------------------------------------------


class TestValidateLicenseJWT:
    def test_valid_free_tier(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, tier="free")
        with _patch_public_key(pub_pem):
            result = validate_license_jwt(token)
        assert result == PluginTier.FREE

    def test_valid_pro_tier(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, tier="pro")
        with _patch_public_key(pub_pem):
            result = validate_license_jwt(token)
        assert result == PluginTier.PRO

    def test_valid_enterprise_tier(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, tier="enterprise")
        with _patch_public_key(pub_pem):
            result = validate_license_jwt(token)
        assert result == PluginTier.ENTERPRISE

    def test_expired_jwt_raises(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, expired=True)
        with _patch_public_key(pub_pem), pytest.raises(LicenseValidationError, match="expired"):
            validate_license_jwt(token)

    def test_wrong_issuer_raises(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, bad_iss=True)
        with _patch_public_key(pub_pem), pytest.raises(LicenseValidationError, match="issuer"):
            validate_license_jwt(token)

    def test_tampered_signature_raises(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, tier="enterprise")
        # Replace the signature segment entirely with 88 'A' chars (valid base64url length,
        # but guaranteed wrong bytes)
        header, payload_seg, _ = token.rsplit(".", 2)
        tampered = f"{header}.{payload_seg}.{'A' * 88}"
        with _patch_public_key(pub_pem), pytest.raises(LicenseValidationError):
            validate_license_jwt(tampered)

    def test_wrong_key_raises(self, keypair):
        priv_pem, _ = keypair
        # Sign with correct key but validate with a different public key
        other_priv = Ed25519PrivateKey.generate()
        other_pub = other_priv.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        token = _make_token(priv_pem)
        with (
            patch("octantis.licensing.validator._PUBLIC_KEY_PEM", other_pub),
            pytest.raises(LicenseValidationError),
        ):
            validate_license_jwt(token)

    def test_malformed_token_raises(self, keypair):
        _, pub_pem = keypair
        with _patch_public_key(pub_pem), pytest.raises(LicenseValidationError, match="malformed"):
            validate_license_jwt("not.a.jwt")

    def test_unknown_tier_raises(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, tier="diamond")
        with _patch_public_key(pub_pem), pytest.raises(LicenseValidationError, match="unknown tier"):
            validate_license_jwt(token)

    def test_missing_tier_claim_raises(self, keypair):
        priv_pem, pub_pem = keypair
        now = int(time.time())
        token = jwt.encode(
            {"iss": "octantis", "iat": now, "exp": now + 3600},
            priv_pem,
            algorithm="EdDSA",
        )
        with _patch_public_key(pub_pem), pytest.raises(LicenseValidationError):
            validate_license_jwt(token)


# ---------------------------------------------------------------------------
# resolve_tier tests
# ---------------------------------------------------------------------------


class TestResolveTier:
    def test_no_env_var_returns_free(self, keypair):
        _, pub_pem = keypair
        with _patch_public_key(pub_pem), patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OCTANTIS_LICENSE_JWT", None)
            from octantis.licensing.validator import resolve_tier
            assert resolve_tier() == PluginTier.FREE

    def test_valid_token_returns_correct_tier(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, tier="pro")
        with _patch_public_key(pub_pem), patch.dict("os.environ", {"OCTANTIS_LICENSE_JWT": token}):
            from octantis.licensing.validator import resolve_tier
            assert resolve_tier() == PluginTier.PRO

    def test_invalid_token_falls_back_to_free(self, keypair):
        _, pub_pem = keypair
        with _patch_public_key(pub_pem), patch.dict("os.environ", {"OCTANTIS_LICENSE_JWT": "bad.token.here"}):
            from octantis.licensing.validator import resolve_tier
            assert resolve_tier() == PluginTier.FREE

    def test_expired_token_falls_back_to_free(self, keypair):
        priv_pem, pub_pem = keypair
        token = _make_token(priv_pem, expired=True)
        with _patch_public_key(pub_pem), patch.dict("os.environ", {"OCTANTIS_LICENSE_JWT": token}):
            from octantis.licensing.validator import resolve_tier
            assert resolve_tier() == PluginTier.FREE


# ---------------------------------------------------------------------------
# PlanGatingEngine tests
# ---------------------------------------------------------------------------

def _make_plugin(name: str, ptype_value: str):
    """Build a minimal LoadedPlugin mock."""
    from octantis.plugins.registry import LoadedPlugin, PluginType

    ptype = PluginType(ptype_value)
    return LoadedPlugin(
        name=name,
        type=ptype,
        instance=MagicMock(),
        source_package="test",
        version="0.0.1",
    )


class TestPlanGatingEngine:
    # --- free tier ---
    def test_free_1_mcp_passes(self):
        engine = PlanGatingEngine(tier=PluginTier.FREE)
        plugins = [_make_plugin("grafana-mcp", "mcp"), _make_plugin("slack", "notifiers")]
        engine.enforce(plugins)  # no exception

    def test_free_2_mcp_raises(self):
        engine = PlanGatingEngine(tier=PluginTier.FREE)
        plugins = [_make_plugin("grafana-mcp", "mcp"), _make_plugin("k8s-mcp", "mcp")]
        with pytest.raises(GatingViolationError, match="mcp"):
            engine.enforce(plugins)

    def test_free_2_notifiers_raises(self):
        engine = PlanGatingEngine(tier=PluginTier.FREE)
        plugins = [
            _make_plugin("slack", "notifiers"),
            _make_plugin("discord", "notifiers"),
        ]
        with pytest.raises(GatingViolationError, match="notifiers"):
            engine.enforce(plugins)

    def test_free_any_ui_raises(self):
        engine = PlanGatingEngine(tier=PluginTier.FREE)
        plugins = [_make_plugin("dashboard", "ui")]
        with pytest.raises(GatingViolationError, match="ui"):
            engine.enforce(plugins)

    # --- pro tier ---
    def test_pro_3_mcp_passes(self):
        engine = PlanGatingEngine(tier=PluginTier.PRO)
        plugins = [
            _make_plugin("grafana-mcp", "mcp"),
            _make_plugin("k8s-mcp", "mcp"),
            _make_plugin("docker-mcp", "mcp"),
        ]
        engine.enforce(plugins)  # no exception

    def test_pro_4_mcp_raises(self):
        engine = PlanGatingEngine(tier=PluginTier.PRO)
        plugins = [
            _make_plugin("grafana-mcp", "mcp"),
            _make_plugin("k8s-mcp", "mcp"),
            _make_plugin("docker-mcp", "mcp"),
            _make_plugin("aws-mcp", "mcp"),
        ]
        with pytest.raises(GatingViolationError, match="mcp"):
            engine.enforce(plugins)

    def test_pro_3_notifiers_passes(self):
        engine = PlanGatingEngine(tier=PluginTier.PRO)
        plugins = [
            _make_plugin("slack", "notifiers"),
            _make_plugin("discord", "notifiers"),
            _make_plugin("pagerduty", "notifiers"),
        ]
        engine.enforce(plugins)  # no exception

    def test_pro_ui_still_raises(self):
        engine = PlanGatingEngine(tier=PluginTier.PRO)
        plugins = [_make_plugin("dashboard", "ui")]
        with pytest.raises(GatingViolationError, match="ui"):
            engine.enforce(plugins)

    # --- enterprise tier ---
    def test_enterprise_4_mcp_passes(self):
        engine = PlanGatingEngine(tier=PluginTier.ENTERPRISE)
        plugins = [
            _make_plugin("grafana-mcp", "mcp"),
            _make_plugin("k8s-mcp", "mcp"),
            _make_plugin("docker-mcp", "mcp"),
            _make_plugin("aws-mcp", "mcp"),
        ]
        engine.enforce(plugins)  # no exception

    def test_enterprise_1_ui_passes(self):
        engine = PlanGatingEngine(tier=PluginTier.ENTERPRISE)
        plugins = [_make_plugin("dashboard", "ui")]
        engine.enforce(plugins)  # no exception

    def test_enterprise_2_ui_raises(self):
        engine = PlanGatingEngine(tier=PluginTier.ENTERPRISE)
        plugins = [_make_plugin("dash1", "ui"), _make_plugin("dash2", "ui")]
        with pytest.raises(GatingViolationError, match="ui"):
            engine.enforce(plugins)

    # --- multiple violations ---
    def test_multiple_violations_reported_together(self):
        engine = PlanGatingEngine(tier=PluginTier.FREE)
        plugins = [
            _make_plugin("grafana-mcp", "mcp"),
            _make_plugin("k8s-mcp", "mcp"),
            _make_plugin("slack", "notifiers"),
            _make_plugin("discord", "notifiers"),
        ]
        with pytest.raises(GatingViolationError) as exc_info:
            engine.enforce(plugins)
        msg = str(exc_info.value)
        assert "mcp" in msg
        assert "notifiers" in msg

    # --- processors, ingesters, storage are never gated ---
    def test_processors_not_gated(self):
        engine = PlanGatingEngine(tier=PluginTier.FREE)
        plugins = [
            _make_plugin("filter-1", "processors"),
            _make_plugin("filter-2", "processors"),
            _make_plugin("filter-3", "processors"),
        ]
        engine.enforce(plugins)  # no exception
