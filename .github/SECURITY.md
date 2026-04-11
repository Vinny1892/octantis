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

### Docker MCP

The Docker MCP server requires access to the Docker socket (`/var/run/docker.sock`). This is inherently privileged — any process with Docker socket access can control the host.

**Mitigations:**

1. **Read-only mode**: Configure the Docker MCP to expose only read-only operations (inspect, logs, stats). Disable any tools that can start, stop, or modify containers.
2. **Socket proxy**: Use a Docker socket proxy (e.g., [Tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy)) that filters API calls. Allow only `GET` methods and specific endpoints (`/containers/json`, `/containers/{id}/json`, `/containers/{id}/logs`, `/containers/{id}/stats`).
3. **Network isolation**: Run the Docker MCP server on the same host as the Docker daemon. Do not expose the Docker socket over TCP without TLS + client certificates.

| Scenario | Protected? |
|---|---|
| LLM stops/removes a container | Yes (if read-only mode or socket proxy) |
| LLM reads container logs | No — all container logs are accessible |
| LLM inspects container environment variables | No — `docker inspect` exposes env vars (may contain secrets) |
| LLM reads host filesystem via Docker | Yes (if read-only mode prevents `docker exec`) |

**Recommendation:** Always use a Docker socket proxy in production. Never mount `/var/run/docker.sock` directly into the MCP container without filtering.

### AWS MCP

The AWS MCP server requires IAM credentials with access to AWS APIs. The LLM autonomously decides which API calls to make.

**Mitigations:**

1. **Least-privilege IAM policy**: Create a dedicated IAM user or role with only the read-only permissions needed:

```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "ec2:DescribeInstances",
            "ec2:DescribeInstanceStatus",
            "cloudwatch:GetMetricData",
            "cloudwatch:ListMetrics",
            "ecs:DescribeTasks",
            "ecs:DescribeServices",
            "ecs:ListTasks",
            "logs:GetLogEvents",
            "logs:FilterLogEvents"
        ],
        "Resource": "*"
    }]
}
```

2. **No write permissions**: Never grant `RunInstances`, `TerminateInstances`, `StopInstances`, `UpdateService`, or any mutating actions.
3. **Credential management**: Use IAM roles (IRSA on EKS, instance profiles on EC2) instead of static access keys. If static keys are required, rotate them regularly and store them in a secrets manager.
4. **Region scoping**: If possible, scope the IAM policy to specific regions using `Condition` blocks.

| Scenario | Protected? |
|---|---|
| LLM terminates an EC2 instance | Yes (if IAM policy is read-only) |
| LLM reads CloudWatch metrics from other accounts | Yes (IAM is account-scoped by default) |
| LLM reads logs containing sensitive data | No — CloudWatch Logs access is broad |
| LLM describes all instances in the account | No — `DescribeInstances` returns all instances |

**Recommendation:** Start with the minimal IAM policy above and expand only as needed. Use AWS CloudTrail to audit API calls made by the AWS MCP credentials.

### Recommendations for production

1. **Always use `--enabled-tools=prometheus,loki`** on mcp-grafana. Never deploy without this flag in environments where Grafana has datasources beyond Prometheus and Loki.
2. **Use a dedicated Grafana organization** if you need stronger isolation — the service account in one org cannot see datasources from another org.
3. **Grafana Enterprise/Cloud** supports per-datasource RBAC scopes (e.g., `datasources:uid:prometheus-prod`). If available, configure the service account token with scoped permissions for an additional layer of defense.
4. **Review Grafana datasources** before deploying Octantis. Ensure no datasource with sensitive data is accessible to the Viewer role without intent.

## Reporting Vulnerabilities

If you find a security issue, please open a GitHub issue or contact the maintainer directly.

## Helm Chart — Secrets Management

The Octantis Helm chart supports three secrets management modes, controlled via `values.yaml`:

### Mode 1: Chart-managed Kubernetes Secrets (`create: true`)

The chart creates native Kubernetes Secrets from values. Suitable for development only — secret values are stored in Helm release data (etcd).

```yaml
secrets:
  anthropicApiKey:
    create: true
    value: "sk-ant-..."
```

### Mode 2: Existing Secret references (`existingSecret`)

The chart references a pre-existing Kubernetes Secret. Use with External Secrets Operator, Sealed Secrets, or manual Secret management.

```yaml
secrets:
  anthropicApiKey:
    existingSecret: "my-vault-secret"
```

### Mode 3: ExternalSecret CR (`externalsecret.create`)

The chart creates ExternalSecret CRs that sync secrets from external backends (Vault, AWS Secrets Manager, GCP Secret Manager) via External Secrets Operator.

```yaml
secrets:
  anthropicApiKey:
    externalsecret:
      create: true
      spec:
        secretStoreRef:
          name: vault-backend
          kind: ClusterSecretStore
        remoteRef:
          key: secret/octantis/anthropic-key
```

**Priority**: `existingSecret` > `externalsecret` > `create`. No sensitive values are stored in `values.yaml` defaults.

### Pod Security

- All containers run as non-root where the base image supports it
- No `privileged: true` or `hostNetwork: true` by default
- SecurityContext is configurable via values for each component
- K8s MCP ClusterRole is strictly read-only (`get`, `list`, `watch`) — no write verbs
