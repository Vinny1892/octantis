## ADDED Requirements

### Requirement: Helm lint in CI
The CI pipeline SHALL run `helm lint charts/octantis/` on every PR that modifies files under `charts/`. The job SHALL fail on any warnings or errors.

#### Scenario: Lint runs on chart changes
- **WHEN** a PR modifies files under `charts/`
- **THEN** the CI SHALL run `helm lint charts/octantis/` and fail if lint reports warnings or errors

#### Scenario: Lint does not block non-chart PRs
- **WHEN** a PR does not modify files under `charts/`
- **THEN** the helm lint job MAY still run but SHALL NOT be a required check

### Requirement: Template matrix test for all toggle combinations
The CI SHALL run `helm template` for all 16 toggle combinations (2^4: otelCollector, otelOperator, grafanaMcp, k8sMcp) on every PR that modifies files under `charts/`.

#### Scenario: All 16 combinations render
- **WHEN** a PR modifies files under `charts/`
- **THEN** the CI SHALL test all 16 toggle combinations via `helm template`
- **AND** SHALL fail if any combination produces a rendering error

#### Scenario: Toggle combination includes all dimensions
- **WHEN** the template matrix runs
- **THEN** it SHALL cover: otelCollector=true/false, otelOperator=true/false, grafanaMcp=true/false, k8sMcp=true/false

### Requirement: Helm CI job runs in existing workflow
The helm validation SHALL run as a job in the existing `.github/workflows/ci.yml`, in parallel with existing lint and test jobs.

#### Scenario: Helm job in ci.yml
- **WHEN** `.github/workflows/ci.yml` is read
- **THEN** it SHALL contain a `helm` job with lint and template matrix steps

### Requirement: Tag-based chart publishing
Pushing a `chart-v*` git tag SHALL trigger a GitHub Actions workflow that lints, tests all toggle combinations, packages, pushes to ghcr.io, and creates a GitHub Release.

#### Scenario: Tag push triggers publish workflow
- **WHEN** a tag matching `chart-v*` is pushed
- **THEN** the workflow SHALL run `helm lint`, `helm template` for all 16 combinations, `helm package`, `helm push` to ghcr.io, and create a GitHub Release

#### Scenario: Duplicate version rejected
- **WHEN** the chart version already exists on ghcr.io
- **THEN** the CI SHALL fail with a clear error and SHALL NOT overwrite the existing version

### Requirement: OCI push to ghcr.io
The chart SHALL be pushed as an OCI artifact to `ghcr.io/vinny1892/charts/octantis`.

#### Scenario: Chart pullable from ghcr.io
- **WHEN** the publish workflow completes
- **THEN** `helm pull oci://ghcr.io/vinny1892/charts/octantis` SHALL succeed

### Requirement: GitHub Release with git-cliff changelog
The publish workflow SHALL generate a changelog scoped to `charts/` changes via git-cliff and attach it and the `.tgz` artifact to a GitHub Release.

#### Scenario: Release includes changelog and artifact
- **WHEN** the publish workflow completes
- **THEN** the GitHub Release SHALL contain a git-cliff generated changelog and the packaged `.tgz` chart

### Requirement: ArtifactHub metadata
The repo SHALL include `artifacthub-repo.yml` at the root. Chart.yaml SHALL include ArtifactHub annotations.

#### Scenario: ArtifactHub repo file exists
- **WHEN** the repo root is listed
- **THEN** `artifacthub-repo.yml` SHALL exist with owner information

#### Scenario: Chart.yaml includes ArtifactHub annotations
- **WHEN** `Chart.yaml` is read
- **THEN** it SHALL include `annotations.artifacthub.io/license` and `annotations.artifacthub.io/changes`

### Requirement: Helm dependency update in CI
All CI steps SHALL run `helm dependency update charts/octantis/` before lint or template to ensure subchart dependencies are resolved.

#### Scenario: Dependency update runs before lint
- **WHEN** the helm CI job runs
- **THEN** `helm dependency update` SHALL run before `helm lint`
