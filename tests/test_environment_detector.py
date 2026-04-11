"""Tests for EnvironmentDetector."""

from octantis.models.event import (
    AWSResource,
    DockerResource,
    InfraEvent,
    K8sResource,
    OTelResource,
)
from octantis.pipeline.environment_detector import EnvironmentDetector


def _make_event(extra: dict | None = None, **resource_kwargs) -> InfraEvent:
    kwargs = {"service_name": "test-svc", **resource_kwargs}
    if extra:
        kwargs["extra"] = extra
    return InfraEvent(
        event_id="test-001",
        event_type="metric",
        source="test-svc",
        resource=OTelResource(**kwargs),
    )


class TestK8sDetection:
    def test_detect_from_pod_name(self):
        event = _make_event(extra={"k8s.pod.name": "api-abc123"})
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, K8sResource)
        assert result.resource.k8s_pod_name == "api-abc123"
        assert result.resource.service_name == "test-svc"

    def test_detect_from_namespace(self):
        event = _make_event(extra={"k8s.namespace.name": "production"})
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, K8sResource)
        assert result.resource.k8s_namespace == "production"

    def test_all_k8s_fields_mapped(self):
        event = _make_event(extra={
            "k8s.namespace.name": "default",
            "k8s.pod.name": "pod-abc",
            "k8s.node.name": "node-1",
            "k8s.deployment.name": "deploy-v1",
        })
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, K8sResource)
        assert result.resource.k8s_namespace == "default"
        assert result.resource.k8s_pod_name == "pod-abc"
        assert result.resource.k8s_node_name == "node-1"
        assert result.resource.k8s_deployment_name == "deploy-v1"


class TestDockerDetection:
    def test_detect_from_container_runtime(self):
        event = _make_event(extra={
            "container.runtime": "docker",
            "container.id": "abc123",
            "container.name": "my-container",
            "container.image.name": "nginx:latest",
        })
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, DockerResource)
        assert result.resource.container_runtime == "docker"
        assert result.resource.container_id == "abc123"
        assert result.resource.container_name == "my-container"
        assert result.resource.image_name == "nginx:latest"

    def test_detect_from_container_id_only(self):
        event = _make_event(extra={"container.id": "def456"})
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, DockerResource)
        assert result.resource.container_id == "def456"


class TestAWSDetection:
    def test_detect_from_cloud_provider(self):
        event = _make_event(extra={
            "cloud.provider": "aws",
            "cloud.region": "us-east-1",
            "host.id": "i-1234567890",
            "cloud.account.id": "123456789012",
            "cloud.platform": "ec2",
        })
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, AWSResource)
        assert result.resource.cloud_provider == "aws"
        assert result.resource.cloud_region == "us-east-1"
        assert result.resource.instance_id == "i-1234567890"
        assert result.resource.account_id == "123456789012"
        assert result.resource.aws_service == "ec2"


class TestEKSPriority:
    def test_k8s_takes_priority_over_aws(self):
        event = _make_event(extra={
            "k8s.pod.name": "pod-in-eks",
            "cloud.provider": "aws",
            "cloud.region": "us-east-1",
        })
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, K8sResource)
        assert result.resource.k8s_pod_name == "pod-in-eks"


class TestExplicitOverride:
    def test_docker_override(self):
        event = _make_event(extra={"k8s.pod.name": "pod-abc"})
        result = EnvironmentDetector(platform_override="docker").detect(event)
        assert isinstance(result.resource, DockerResource)

    def test_aws_override(self):
        event = _make_event(extra={"k8s.pod.name": "pod-abc"})
        result = EnvironmentDetector(platform_override="aws").detect(event)
        assert isinstance(result.resource, AWSResource)

    def test_k8s_override(self):
        event = _make_event(extra={"cloud.provider": "aws"})
        result = EnvironmentDetector(platform_override="k8s").detect(event)
        assert isinstance(result.resource, K8sResource)


class TestDefaultFallback:
    def test_default_to_k8s_when_no_indicators(self):
        event = _make_event()
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, K8sResource)


class TestFieldPreservation:
    def test_all_base_fields_preserved(self):
        event = InfraEvent(
            event_id="test-001",
            event_type="metric",
            source="test-svc",
            resource=OTelResource(
                service_name="my-app",
                service_namespace="prod",
                host_name="node-1",
                extra={
                    "k8s.pod.name": "pod-abc",
                    "custom.label": "value",
                },
            ),
        )
        result = EnvironmentDetector().detect(event)
        assert isinstance(result.resource, K8sResource)
        assert result.resource.service_name == "my-app"
        assert result.resource.service_namespace == "prod"
        assert result.resource.host_name == "node-1"
        assert result.resource.extra.get("custom.label") == "value"
        assert result.resource.k8s_pod_name == "pod-abc"
