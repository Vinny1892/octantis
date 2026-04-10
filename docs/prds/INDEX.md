# PRD Index

> Auto-generated — do not edit manually

| # | Title | Summary | Priority | Effort | Owner | Tags | Created |
|---|-------|---------|----------|--------|-------|------|---------|
| 001 | [Direct OTLP Ingestion — Redpanda Removal](prd-001-otlp-direct-ingestion.md) | Remove Redpanda/Kafka from the ingestion stack and receive OTLP events directly via gRPC and HTTP in Octantis | media | medium | Vinicius Espindola | architecture, otlp, ingestion | 2026-04-05 |
| 002 | [Grafana MCP Analysis — Trigger-Based Investigation](prd-002-grafana-mcp-analysis.md) | Replace static enrichment with LLM-driven analysis via Grafana MCP, using OTLP events as triggers and querying Prometheus/Loki directly for investigation | alta | medium | Vinicius Espindola | architecture, grafana, mcp, llm, prometheus, loki, pipeline | 2026-04-06 |
| 003 | [Multi-Platform Support — Docker & AWS](prd-003-multi-platform-docker-aws.md) | Expand Octantis to support Docker and AWS environments via platform detection, Node Exporter compatibility, Docker MCP, and AWS MCP integrations | media | medium | Vinicius Espindola | architecture, docker, aws, mcp, node-exporter, multi-platform | 2026-04-09 |
| 004 | [Octantis Helm Chart — Modular Deployment](prd-004-helm-chart.md) | Create a modular Helm chart for Octantis with toggleable components (OTel Collector, OTel Operator, Grafana MCP, K8s MCP, kube-prometheus-stack) published to ghcr.io and ArtifactHub | media | medium | Vinicius Espindola | helm, kubernetes, deployment, distribution, otel, mcp, prometheus, monitoring | 2026-04-10 |

## Dependency Graph

```mermaid
flowchart LR
    PRD001["001: Direct OTLP Ingestion"] --> PRD002["002: Grafana MCP Analysis"]
    PRD001 --> PRD003["003: Multi-Platform Docker & AWS"]
    PRD002 --> PRD003
    PRD001 --> PRD004["004: Helm Chart"]
    PRD002 --> PRD004
```
