## ADDED Requirements

### Requirement: PlanGatingEngine enforces tier limits at registry load time
The `PlanGatingEngine` MUST run after plugin discovery and before any plugin's `setup()` is invoked. It MUST count loaded plugins by type and compare against tier limits: free tier allows 1 MCPConnector and 1 Notifier and 0 UIProvider; pro tier allows 3 MCPConnectors and 3 Notifiers and 0 UIProvider; enterprise tier allows unlimited MCPConnectors and Notifiers and 1 UIProvider. When limits are exceeded, the engine MUST fail startup with a clear operator-facing error naming the tier, the limit, and the excess plugin.

#### Scenario: Free tier with two MCP connectors rejected
- **WHEN** Octantis starts with no license and two MCPConnector plugins installed
- **THEN** startup fails with an error stating `free tier allows 1 MCPConnector; 2 are installed: <plugin-a>, <plugin-b>; upgrade to pro or remove one`

#### Scenario: Pro tier with three notifiers accepted
- **WHEN** Octantis starts with a valid pro-tier JWT and three Notifier plugins installed
- **THEN** startup proceeds and all three notifiers load

#### Scenario: Enterprise tier allows UIProvider
- **WHEN** Octantis starts with a valid enterprise-tier JWT and one UIProvider plugin installed
- **THEN** the UIProvider loads; without an enterprise JWT, loading the UIProvider fails with an error

### Requirement: License JWTs are validated offline using Ed25519
License tokens MUST be JWTs signed with Ed25519. Validation MUST use the public key embedded in the core package and MUST NOT make network calls. The JWT MUST carry at minimum `tier` (one of `free`, `pro`, `enterprise`), `iss` (issuer), `iat` (issued-at), and `exp` (expiry). Verification MUST fail if the signature is invalid, the token is expired, the issuer is unknown, or required claims are missing.

#### Scenario: Valid pro-tier JWT accepted
- **WHEN** `OCTANTIS_LICENSE_JWT` is set to a token signed by the known Ed25519 private key with `tier=pro` and a future `exp`
- **THEN** the gating engine resolves the tier as `pro`

#### Scenario: Tampered JWT rejected
- **WHEN** the JWT payload is modified without resigning
- **THEN** validation fails with `invalid_signature` and startup aborts

#### Scenario: Expired JWT rejected
- **WHEN** the JWT's `exp` claim is in the past
- **THEN** validation fails with `expired_license` and startup aborts

#### Scenario: Missing JWT defaults to free tier
- **WHEN** `OCTANTIS_LICENSE_JWT` is unset
- **THEN** the gating engine resolves the tier as `free`

### Requirement: Gating errors are actionable for operators
Every gating failure MUST log at `ERROR` level with fields `tier`, `limit`, `installed_count`, `plugin_names`, and a suggested remediation (upgrade path or plugin to remove). Error messages MUST NOT leak license internals (e.g., the public key or raw JWT contents).

#### Scenario: Error message names the remediation
- **WHEN** a free-tier deployment exceeds the notifier slot limit
- **THEN** the error log includes a line like `remediation: upgrade to pro (3 slots) or remove one of: <plugin-a>, <plugin-b>`
