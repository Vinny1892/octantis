# Security

## Grafana MCP — Datasource Access Control

Octantis queries Prometheus and Loki via a Grafana MCP server. Since Grafana OSS does not support per-datasource permissions (that is an Enterprise/Cloud feature), any service account with Viewer role can query **all** datasources in the organization — including potentially sensitive ones like PostgreSQL, MySQL, or Elasticsearch.

This is a problem because the LLM autonomously decides which queries to execute. Without restrictions, it could read data from datasources outside the intended scope.

### How Octantis mitigates this

The Grafana MCP server supports an `--enabled-tools` flag that whitelists which tool categories are exposed. Octantis deploys mcp-grafana with:

```
--enabled-tools=prometheus,loki
```

This means the MCP server **only** exposes Prometheus and Loki query tools to the LLM. Tools for querying generic datasources (PostgreSQL, MySQL, etc.), managing dashboards, searching, or any other Grafana functionality are not registered and cannot be called.

Additionally, the following Grafana Cloud features are explicitly disabled since they are not supported:

```
--disable-oncall
--disable-incident
--disable-sift
```

### What this protects against

| Scenario | Protected? |
|---|---|
| LLM queries a PostgreSQL datasource with sensitive data | Yes — `datasource` category tools are not enabled |
| LLM queries arbitrary Prometheus metrics | No — any Prometheus-type datasource is queryable |
| LLM queries arbitrary Loki logs | No — any Loki-type datasource is queryable |
| LLM creates/modifies Grafana dashboards | Yes — `dashboard` category tools are not enabled |
| LLM lists all datasources in Grafana | Yes — `datasource`/`search` category tools are not enabled |

### Grafana Service Account

The Grafana service account used by mcp-grafana must have the **Viewer** role (minimum required for read-only queries). This is enforced in:

- `dev/setup.sh` — creates the service account with `"role":"Viewer"`
- `dev/manifests/mcp-grafana.yaml` — dev cluster deployment
- `examples/kubernetes/mcp-grafana.yaml` — production example

### Kubernetes MCP

The Kubernetes MCP server (`mcp-k8s`) runs with a dedicated ServiceAccount restricted to read-only verbs (`get`, `list`, `watch`) via ClusterRole RBAC. It cannot modify any cluster resources.

### Recommendations for production

1. **Always use `--enabled-tools=prometheus,loki`** on mcp-grafana. Never deploy without this flag in environments where Grafana has datasources beyond Prometheus and Loki.
2. **Use a dedicated Grafana organization** if you need stronger isolation — the service account in one org cannot see datasources from another org.
3. **Grafana Enterprise/Cloud** supports per-datasource RBAC scopes (e.g., `datasources:uid:prometheus-prod`). If available, configure the service account token with scoped permissions for an additional layer of defense.
4. **Review Grafana datasources** before deploying Octantis. Ensure no datasource with sensitive data is accessible to the Viewer role without intent.

## Reporting Vulnerabilities

If you find a security issue, please open a GitHub issue or contact the maintainer directly.
