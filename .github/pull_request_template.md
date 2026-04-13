## Summary

<!-- What does this PR do and why? 1-3 sentences. -->

## Changes

<!-- Bullet list of what changed. -->

-

## How to test

<!-- Steps to verify this works. -->

1.

## Checklist

- [ ] Tests pass (`uv run pytest`)
- [ ] Lint passes (`uv run ruff check src/ tests/`)
- [ ] Coverage ≥ 94% (`uv run pytest --cov=octantis --cov-fail-under=94`)
- [ ] New `.py` files under `src/octantis/` have `# SPDX-License-Identifier: AGPL-3.0-or-later`
- [ ] New `.py` files under `packages/octantis-plugin-sdk/src/` have `# SPDX-License-Identifier: Apache-2.0`
- [ ] Tests reviewed against Protocol boundaries (not just "make green")
- [ ] Docs updated (`AGENTS.md`, operator guides, specs) if behavior changed
