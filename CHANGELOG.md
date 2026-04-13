# Changelog

All notable changes to this project will be documented in this file.
Versions follow [Semantic Versioning](https://semver.org/).
## [Unreleased]

### Bug Fixes

- **lint:** resolve ruff errors in multi-platform code ([Vinny1892](https://github.com/Vinny1892))

- **ci:** remove helm dependency update to avoid upstream schema bug ([Vinny1892](https://github.com/Vinny1892))

- restrict mcp-grafana to prometheus+loki tools only ([Vinny1892](https://github.com/Vinny1892))

- repair truncated JSON when LLM response is cut inside a string value ([Vinny1892](https://github.com/Vinny1892))

- repair truncated JSON from LLM responses ([Vinny1892](https://github.com/Vinny1892))

- disable Grafana Cloud-only tools in mcp-grafana (oncall, incident, sift) ([Vinny1892](https://github.com/Vinny1892))

- handle truncated markdown fences in LLM JSON responses ([Vinny1892](https://github.com/Vinny1892))

- strip markdown fences from LLM JSON responses in analyzer and planner ([Vinny1892](https://github.com/Vinny1892))

- handle MCP tools with dict args_schema instead of Pydantic model ([Vinny1892](https://github.com/Vinny1892))

- use correct mcp-grafana image, port and env var ([Vinny1892](https://github.com/Vinny1892))

- resolve ruff SIM105 lint errors in MCP client manager ([Vinny1892](https://github.com/Vinny1892))

- clean up partial SSE contexts on MCP connection failure ([Vinny1892](https://github.com/Vinny1892))

- copy README.md into Docker builder stage ([Vinny1892](https://github.com/Vinny1892))

- fix mermaid diagram in agent.md and add doc links to README ([Vinny1892](https://github.com/Vinny1892))


### Documentation

- add Tech Spec 005 — Plugin Architecture & Open-Core Foundation ([Vinny1892](https://github.com/Vinny1892))

- add PRD 005 — Plugin Architecture & Open-Core Foundation ([Vinny1892](https://github.com/Vinny1892))

- add PRD 003, PRD 004, Tech Spec 003, Tech Spec 004 ([Vinny1892](https://github.com/Vinny1892))

- rename .github doc files to uppercase ([Vinny1892](https://github.com/Vinny1892))

- move agent, overview, onboarding, pipeline to .github/ ([Vinny1892](https://github.com/Vinny1892))

- rename Table of Contents to List of Contents ([Vinny1892](https://github.com/Vinny1892))

- move contributing guide to .github/CONTRIBUTING.md ([Vinny1892](https://github.com/Vinny1892))

- add badges to README (CI, mcp-grafana, GHCR, Python) ([Vinny1892](https://github.com/Vinny1892))

- move dev setup under Running Octantis, add Contributing section ([Vinny1892](https://github.com/Vinny1892))

- clarify README sections - separate running from contributing ([Vinny1892](https://github.com/Vinny1892))

- add table of contents to all project documentation ([Vinny1892](https://github.com/Vinny1892))

- translate all docs to English and use infrastructure-neutral wording ([Vinny1892](https://github.com/Vinny1892))

- remove service/URL table from README quickstart ([Vinny1892](https://github.com/Vinny1892))

- rewrite README and onboarding for Kubernetes-first workflow ([Vinny1892](https://github.com/Vinny1892))

- minor wording fix in dev README ([Vinny1892](https://github.com/Vinny1892))

- update dev README to reflect K8s MCP connection in Octantis ([Vinny1892](https://github.com/Vinny1892))

- document Kubernetes MCP server image and auth model ([Vinny1892](https://github.com/Vinny1892))

- rewrite technical docs for MCP-driven architecture ([Vinny1892](https://github.com/Vinny1892))


### Features

- Phases 5-7 — distributed runtime, Helm, AGPL-3.0 migration, CI policy

- **runtime:** Phase 4 — concurrent standalone mode (TaskGroup + semaphore) ([Vinny1892](https://github.com/Vinny1892))

- **licensing:** Phase 3 — JWT Ed25519 plan gating (free/pro/enterprise) ([Vinny1892](https://github.com/Vinny1892))

- **plugins:** Phase 2 complete — per-transport Ingesters + SDK Event boundary (Fork C=1) ([Vinny1892](https://github.com/Vinny1892))

- **plugins:** Phase 2 partial — plugin SDK, registry, and per-server MCP split (Fork B=1) ([Vinny1892](https://github.com/Vinny1892))

- add multi-platform support (Docker, AWS) with MCP slot model ([Vinny1892](https://github.com/Vinny1892))

- **helm:** add kube-prometheus-stack as conditional subchart ([Vinny1892](https://github.com/Vinny1892))

- add modular Helm chart with three-mode secrets support ([Vinny1892](https://github.com/Vinny1892))

- replace NodePort with MetalLB for proper LoadBalancer in Kind ([Vinny1892](https://github.com/Vinny1892))

- add AWS Bedrock as LLM provider + pin litellm>=1.83.0 ([Vinny1892](https://github.com/Vinny1892))

- add LANGUAGE env var to control LLM output language (en, pt-br) ([Vinny1892](https://github.com/Vinny1892))

- add prometheus receiver to OTel Collector for kube-state-metrics ([Vinny1892](https://github.com/Vinny1892))

- add Kubernetes MCP server to dev environment ([Vinny1892](https://github.com/Vinny1892))

- add Kind dev environment with full observability stack ([Vinny1892](https://github.com/Vinny1892))

- replace static collectors with MCP-driven autonomous investigation ([Vinny1892](https://github.com/Vinny1892))

- replace Redpanda with native OTLP receiver (gRPC + HTTP) ([Vinny1892](https://github.com/Vinny1892))

- initial commit ([Vinny1892](https://github.com/Vinny1892))

