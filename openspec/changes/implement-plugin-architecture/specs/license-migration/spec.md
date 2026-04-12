## ADDED Requirements

### Requirement: Core is licensed under AGPL-3.0
The repository `LICENSE` file MUST be the verbatim AGPL-3.0 license text. `pyproject.toml` MUST declare `license = { text = "AGPL-3.0-or-later" }` and include the matching Trove classifier. The Helm `Chart.yaml` MUST set `annotations.licenses = "AGPL-3.0-or-later"`. README badges MUST display the AGPL-3.0 license.

#### Scenario: LICENSE file is AGPL-3.0
- **WHEN** CI runs the license-file check
- **THEN** the repository `LICENSE` matches the canonical AGPL-3.0 text byte-for-byte

#### Scenario: Package metadata declares AGPL
- **WHEN** `pip show octantis` is run on an installed core package
- **THEN** the License field reads `AGPL-3.0-or-later`

### Requirement: Every source file carries a license header
Every `.py` file under `src/octantis/` MUST begin with the AGPL-3.0 SPDX header `# SPDX-License-Identifier: AGPL-3.0-or-later`. The `octantis-plugin-sdk` source files MUST begin with `# SPDX-License-Identifier: Apache-2.0`. A CI linter MUST fail the build if any source file is missing or carries a mismatched header.

#### Scenario: Missing header fails CI
- **WHEN** a pull request adds a `src/octantis/foo.py` without the SPDX header
- **THEN** CI fails with an error naming the file and the expected header

#### Scenario: SDK carries Apache-2.0 header
- **WHEN** the header linter runs on the SDK package
- **THEN** every source file has `SPDX-License-Identifier: Apache-2.0`

### Requirement: Dependency license audit runs in CI
CI MUST run `pip-licenses` (or equivalent) on the core package's installed dependencies and MUST fail the build if any direct or transitive dependency declares a license incompatible with AGPL-3.0 (e.g., SSPL, BSL, proprietary without explicit allowance). The SDK package MUST be audited independently and MUST fail if any dependency is more restrictive than Apache-2.0 compatibility requires.

#### Scenario: Incompatible dependency rejected
- **WHEN** a dependency declaring SSPL is added to core
- **THEN** the CI license audit fails and names the offending dependency and its license

#### Scenario: Clean audit passes
- **WHEN** all dependencies declare AGPL-compatible licenses
- **THEN** the audit step logs the full license inventory and exits zero

### Requirement: LICENSING.md documents the dual-license model
The repository MUST contain a top-level `LICENSING.md` explaining: (a) core is AGPL-3.0 and what that means for self-hosting, SaaS redistribution, and internal use; (b) the SDK is Apache-2.0 and plugins depending only on the SDK are not obligated to be AGPL; (c) the key differences and an FAQ covering common operator questions.

#### Scenario: LICENSING.md present and linked
- **WHEN** the repository is inspected
- **THEN** `LICENSING.md` exists at the root, is linked from `README.md`, and covers the three topics above

### Requirement: README advertises the license model
The repository `README.md` MUST display a license badge reading `AGPL-3.0` for the core and, where the SDK is referenced, MUST note that the SDK is Apache-2.0. The README MUST link to `LICENSING.md` for details.

#### Scenario: README badges updated
- **WHEN** a reader opens `README.md`
- **THEN** an AGPL-3.0 badge is visible near the top and a link to `LICENSING.md` is present
