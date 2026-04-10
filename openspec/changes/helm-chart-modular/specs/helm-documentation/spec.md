## ADDED Requirements

### Requirement: Chart README with configuration table
The chart SHALL include `charts/octantis/README.md` with a configuration table listing all values, types, defaults, and descriptions.

#### Scenario: README contains configuration table
- **WHEN** `charts/octantis/README.md` is read
- **THEN** it SHALL contain a table with columns: Parameter, Description, Default

#### Scenario: README includes quickstart
- **WHEN** `charts/octantis/README.md` is read
- **THEN** it SHALL include a quickstart section with `helm install` examples

### Requirement: Example values files
The chart SHALL include example values files in `charts/octantis/examples/`: `values-minimal.yaml` (Octantis only), `values-full-stack.yaml` (everything enabled), and `values-external-mcp.yaml` (Octantis + external MCP URLs).

#### Scenario: Minimal example values
- **WHEN** `charts/octantis/examples/values-minimal.yaml` is read
- **THEN** it SHALL contain only Octantis core values with all optional components disabled

#### Scenario: Full stack example values
- **WHEN** `charts/octantis/examples/values-full-stack.yaml` is read
- **THEN** it SHALL enable all components (otelCollector, otelOperator, grafanaMcp, k8sMcp, kubePrometheusStack)

#### Scenario: External MCP example values
- **WHEN** `charts/octantis/examples/values-external-mcp.yaml` is read
- **THEN** it SHALL set `octantis.externalMcp.grafanaUrl` and `octantis.externalMcp.k8sUrl` with MCPs disabled

### Requirement: ONBOARDING.md updated with Helm install
`.github/ONBOARDING.md` SHALL be updated to recommend `helm install` as the primary Kubernetes deployment method.

#### Scenario: Onboarding references helm install
- **WHEN** `.github/ONBOARDING.md` is read
- **THEN** it SHALL include a section about installing Octantis via Helm

### Requirement: OVERVIEW.md updated with chart reference
`.github/OVERVIEW.md` SHALL be updated to reference the Helm chart in the deployment section.

#### Scenario: Overview references chart
- **WHEN** `.github/OVERVIEW.md` is read
- **THEN** it SHALL mention the Helm chart as the recommended deployment method

### Requirement: Documentation follows repository patterns
All chart documentation SHALL follow existing repository patterns: dark-mode Mermaid diagrams, List of Contents sections, and `file_path:line_number` citations.

#### Scenario: README uses Mermaid diagrams
- **WHEN** `charts/octantis/README.md` is read
- **THEN** it SHALL include Mermaid diagrams for architecture visualization
