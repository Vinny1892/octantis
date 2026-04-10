## ADDED Requirements

### Requirement: Three-mode secrets support
Each sensitive value (Anthropic API key, OpenRouter API key, Grafana MCP API key, Slack webhook URL, Discord webhook URL) SHALL support three modes: chart-managed Kubernetes Secret (`create: true`), existing Secret reference (`existingSecret`), and External Secrets Operator (`externalsecret`). Priority: `existingSecret` > `externalsecret.create` > `create`.

#### Scenario: Chart-managed Secret created
- **WHEN** `secrets.anthropicApiKey.create=true` and `secrets.anthropicApiKey.value="sk-ant-xxx"`
- **THEN** the chart SHALL create a Kubernetes Secret with key `ANTHROPIC_API_KEY` and value `sk-ant-xxx`
- **AND** the Octantis Deployment SHALL reference it via `secretKeyRef`

#### Scenario: Existing Secret referenced
- **WHEN** `secrets.anthropicApiKey.existingSecret="my-secret"`
- **THEN** the chart SHALL NOT create a Secret for the Anthropic API key
- **AND** the Octantis Deployment SHALL reference `my-secret` via `secretKeyRef` with key `secrets.anthropicApiKey.key`

#### Scenario: Existing Secret takes priority over create
- **WHEN** `secrets.anthropicApiKey.existingSecret="my-secret"` AND `secrets.anthropicApiKey.create=true`
- **THEN** the chart SHALL NOT create a Secret
- **AND** the Octantis Deployment SHALL reference `my-secret`

### Requirement: External Secrets Operator support
Each sensitive value SHALL support an `externalsecret` block that creates an ExternalSecret CR when `externalsecret.create: true`. The block SHALL accept a full ESO spec including `secretStoreRef`, `refreshInterval`, and `target`.

#### Scenario: ExternalSecret CR created for Anthropic API key
- **WHEN** `secrets.anthropicApiKey.externalsecret.create=true` and `secrets.anthropicApiKey.externalsecret.spec.secretStoreRef.name="vault-backend"` and `secrets.anthropicApiKey.externalsecret.spec.remoteRef.key="secret/octantis/anthropic-key"`
- **THEN** the chart SHALL create an ExternalSecret CR with the provided spec
- **AND** the Octantis Deployment SHALL reference the resulting Secret via `secretKeyRef`

#### Scenario: ExternalSecret with custom refresh interval
- **WHEN** `secrets.anthropicApiKey.externalsecret.create=true` and `secrets.anthropicApiKey.externalsecret.spec.refreshInterval="5m"`
- **THEN** the ExternalSecret CR SHALL set `refreshInterval: 5m`

#### Scenario: ExternalSecret not created when disabled
- **WHEN** `secrets.anthropicApiKey.externalsecret.create=false` (default)
- **THEN** no ExternalSecret CR SHALL be rendered

#### Scenario: Existing Secret takes priority over ExternalSecret
- **WHEN** `secrets.anthropicApiKey.existingSecret="my-secret"` AND `secrets.anthropicApiKey.externalsecret.create=true`
- **THEN** the chart SHALL NOT create a Secret or ExternalSecret CR
- **AND** the Octantis Deployment SHALL reference `my-secret`

### Requirement: ExternalSecret conditional rendering
ExternalSecret CRs SHALL only be rendered when `externalsecret.create: true`. The chart SHALL NOT require External Secrets Operator CRDs to be installed for `helm template` to succeed.

#### Scenario: helm template succeeds without ESO CRDs
- **WHEN** `helm template` is run with `secrets.anthropicApiKey.externalsecret.create=false`
- **THEN** the command SHALL succeed without requiring ExternalSecret CRDs

#### Scenario: NOTES.txt warns when ExternalSecret enabled without ESO
- **WHEN** any `secrets.*.externalsecret.create=true` is set
- **THEN** NOTES.txt SHALL include a reminder that External Secrets Operator must be installed in the cluster

### Requirement: Configurable secret keys
Each secret entry SHALL allow configuring the key name used in `secretKeyRef` and the ExternalSecret target via `secrets.*.key`.

#### Scenario: Custom key name used in secretKeyRef
- **WHEN** `secrets.anthropicApiKey.key="CUSTOM_ANTHROPIC_KEY"` and `secrets.anthropicApiKey.existingSecret="my-secret"`
- **THEN** the Octantis Deployment SHALL reference `my-secret` with key `CUSTOM_ANTHROPIC_KEY`

### Requirement: No sensitive values in defaults
`values.yaml` defaults SHALL never contain secret values. All `value` fields SHALL default to empty string.

#### Scenario: No secret values in defaults
- **WHEN** `values.yaml` is read
- **THEN** every `secrets.*.value` SHALL be `""`

### Requirement: All env vars reference Secrets
All sensitive environment variables on the Octantis pod SHALL use `secretKeyRef`, never plain `value` in the Deployment manifest.

#### Scenario: API key referenced via secretKeyRef
- **WHEN** the Octantis Deployment is rendered with any secrets configuration
- **THEN** `ANTHROPIC_API_KEY` SHALL be set via `secretKeyRef`, never as a plain env var value
