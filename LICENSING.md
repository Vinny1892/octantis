# Licensing

Octantis uses a dual-license model:

| Component | License | Why |
|-----------|---------|-----|
| `src/octantis/` (core) | AGPL-3.0-or-later | Protects against SaaS competitors re-hosting without contributing back |
| `packages/octantis-plugin-sdk/` (SDK) | Apache-2.0 | Lets plugin authors ship proprietary or open-source plugins without copyleft obligations |

## Plan Tiers

Octantis enforces plugin count limits at startup via a JWT license.
Missing JWT → **free tier** (no error, no network call).

| Plugin Type | Free | Pro | Enterprise |
|-------------|------|-----|------------|
| MCP Connectors | 1 | 3 | Unlimited |
| Notifiers | 1 | 1 | Unlimited |
| UI Providers | 0 | 0 | 1 |
| Ingesters | Unlimited | Unlimited | Unlimited |
| Processors | Unlimited | Unlimited | Unlimited |

## Installing a License

Set the environment variable `OCTANTIS_LICENSE_JWT` to the JWT issued by Octantis:

```bash
export OCTANTIS_LICENSE_JWT="eyJhbGci..."
```

The JWT is verified offline against the public key bundled at
`src/octantis/licensing/public_key.pem`. No network call is made.

### Obtaining a License

- **Pro**: contact support@octantis.dev or purchase at octantis.dev/pricing
- **Enterprise**: contact sales@octantis.dev

## AGPL-3.0 FAQ

**Q: Does AGPL affect my internal self-hosted deployment?**  
A: No. AGPL only triggers when you *distribute* the software or offer it *as a network service* to external users. Running Octantis internally for your own team is not distribution.

**Q: Can I write a plugin and keep it proprietary?**  
A: Yes. Plugins depend on `octantis-plugin-sdk` (Apache-2.0), not on the AGPL core. You never distribute or link with the AGPL core code — your plugin is loaded at runtime via entry points. Your plugin code is not a derivative work of the core.

**Q: What if I want to fork the core and offer it as a hosted service?**  
A: AGPL requires you to publish your modifications. You must provide the source of your modified version to all users of your hosted service.

**Q: How do license keys rotate?**  
A: Octantis ships with a bundled public key. When the key rotates, a new public key is included in a patch release. Old JWTs signed with the old key will fail validation after the release. Operators should obtain a new JWT before upgrading.

## Technical Details

- Algorithm: **EdDSA** (Ed25519)
- Validation: offline signature check + `iss`, `exp`, `iat`, `tier` claim verification
- Invalid/expired JWT → logs error, falls back silently to **free tier** (no crash)
- Metrics: `octantis_plan_tier_info{tier="..."}` gauge, `octantis_plan_gating_violations_total{plugin_type="..."}` counter
