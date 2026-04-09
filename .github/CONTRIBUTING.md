# Contributing

1. Fork the repo and create a feature branch from `master`
2. Install dependencies: `uv sync`
3. Make your changes
4. Run tests and lint:
   ```bash
   uv run pytest
   uv run ruff check src/ tests/
   ```
5. Open a pull request against `master`

All tests are mocked — no real LLM, MCP, or external API calls needed to run them.
