# AWS Monitoring Example

Octantis deployment for AWS environments (EC2, ECS, Fargate).

## Architecture

```
EC2 / ECS Instances
  ├── Node Exporter ──► Prometheus ──► Grafana ──► Grafana MCP ─┐
  ├── OTel Collector (hostmetrics + resourcedetection/ec2) ─────►│ Octantis
  ├── AWS MCP (EC2/CloudWatch/ECS read-only) ───────────────────►│   (Bedrock)
  └── Your workloads                                             └──► Slack/Discord
```

## Deployment Options

### Option 1: ECS Fargate Task Definition

Deploy Octantis as a Fargate task with sidecar MCP containers:

```bash
# 1. Create secrets in AWS Secrets Manager
aws secretsmanager create-secret \
  --name octantis/grafana-mcp-key \
  --secret-string "glsa_..."

aws secretsmanager create-secret \
  --name octantis/slack-webhook \
  --secret-string "https://hooks.slack.com/services/..."

# 2. Create IAM role with least-privilege policy
aws iam create-policy \
  --policy-name octantis-policy \
  --policy-document file://iam-policy.json

aws iam create-role \
  --role-name octantis-task-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name octantis-task-role \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/octantis-policy

# 3. Register task definition (edit ACCOUNT_ID in ecs-task-definition.json first)
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json

# 4. Create ECS service
aws ecs create-service \
  --cluster my-cluster \
  --service-name octantis \
  --task-definition octantis \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx]}"
```

### Option 2: Local Docker Compose (simulation)

For local development and testing with simulated AWS resource attributes:

```bash
cd examples/aws

export ANTHROPIC_API_KEY="sk-ant-..."
# Optional: export AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for real AWS MCP

docker compose up -d
```

The OTel Collector adds `cloud.provider=aws`, `cloud.region=us-east-1`, etc. as
resource attributes so Octantis auto-detects the AWS platform.

## Files

| File | Description |
|---|---|
| `ecs-task-definition.json` | ECS Fargate task with Octantis + Grafana MCP + AWS MCP sidecars |
| `iam-policy.json` | Least-privilege IAM policy for Octantis (read-only EC2/CloudWatch/ECS/Logs + Bedrock) |
| `docker-compose.yml` | Local simulation stack |
| `otel-collector-config.yaml` | OTel Collector config with AWS resource attributes |

## IAM Policy

The `iam-policy.json` provides:

- **EC2**: DescribeInstances, DescribeInstanceStatus (read-only)
- **CloudWatch**: GetMetricData, ListMetrics, DescribeAlarms (read-only)
- **ECS**: DescribeTasks, DescribeServices, ListTasks (read-only)
- **CloudWatch Logs**: GetLogEvents, FilterLogEvents (read-only)
- **Bedrock**: InvokeModel (for LLM calls)
- **Secrets Manager**: GetSecretValue for `octantis/*` secrets only

No write permissions are granted. See [SECURITY.md](../../.github/SECURITY.md#aws-mcp) for details.

## Platform Detection

On real EC2/ECS, use the OTel Collector `resourcedetection` processor to
auto-discover instance metadata:

```yaml
processors:
  resourcedetection:
    detectors: [ec2, ecs]
    ec2:
      tags:
        - Name
        - Environment
```

This automatically adds `cloud.provider=aws`, `cloud.region`, `host.id`, and
`cloud.account.id` — Octantis detects these and creates an `AWSResource`.

## Bedrock Configuration

For production AWS deployments, use Bedrock instead of direct Anthropic API:

```env
LLM_PROVIDER=bedrock
LLM_MODEL=global.anthropic.claude-opus-4-6-v1
AWS_REGION_NAME=us-east-1
```

Credentials are resolved via the standard AWS chain (IAM role > env vars > config file).
On ECS, the task role provides Bedrock access automatically.
