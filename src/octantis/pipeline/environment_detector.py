# SPDX-License-Identifier: AGPL-3.0-or-later
"""Environment Detector: promotes base OTelResource to typed subclass.

Inspects OTLP resource attributes (from the extra dict) or explicit
OCTANTIS_PLATFORM config to determine the source platform and create
the appropriate typed resource (K8sResource, DockerResource, AWSResource).
"""

from __future__ import annotations

from typing import Literal

import structlog

from octantis.models.event import (
    AWSResource,
    DockerResource,
    InfraEvent,
    K8sResource,
    OTelResource,
)

log = structlog.get_logger(__name__)


def _promote_k8s(base: OTelResource) -> K8sResource:
    """Promote base resource to K8sResource using extra dict attributes."""
    extra = base.extra
    return K8sResource(
        service_name=base.service_name,
        service_namespace=base.service_namespace,
        host_name=base.host_name,
        extra=base.extra,
        k8s_namespace=extra.get("k8s.namespace.name"),
        k8s_pod_name=extra.get("k8s.pod.name"),
        k8s_node_name=extra.get("k8s.node.name"),
        k8s_deployment_name=extra.get("k8s.deployment.name"),
    )


def _promote_docker(base: OTelResource) -> DockerResource:
    """Promote base resource to DockerResource using extra dict attributes."""
    extra = base.extra
    return DockerResource(
        service_name=base.service_name,
        service_namespace=base.service_namespace,
        host_name=base.host_name,
        extra=base.extra,
        container_id=extra.get("container.id"),
        container_name=extra.get("container.name"),
        container_runtime=extra.get("container.runtime"),
        image_name=extra.get("container.image.name"),
    )


def _promote_aws(base: OTelResource) -> AWSResource:
    """Promote base resource to AWSResource using extra dict attributes."""
    extra = base.extra
    return AWSResource(
        service_name=base.service_name,
        service_namespace=base.service_namespace,
        host_name=base.host_name,
        extra=base.extra,
        cloud_region=extra.get("cloud.region"),
        instance_id=extra.get("host.id"),
        account_id=extra.get("cloud.account.id"),
        aws_service=extra.get("cloud.platform"),
    )


class EnvironmentDetector:
    """Detects the source platform from OTLP resource attributes and promotes
    the base OTelResource to the appropriate typed subclass.

    Detection order (first match wins):
    1. Explicit OCTANTIS_PLATFORM config override
    2. K8s attributes (k8s.pod.name, k8s.namespace.name)
    3. Docker attributes (container.runtime=docker, container.id)
    4. AWS attributes (cloud.provider=aws)
    5. Default to K8s for backwards compatibility
    """

    def __init__(
        self,
        platform_override: Literal["k8s", "docker", "aws"] | None = None,
    ) -> None:
        self._override = platform_override

    def detect(self, event: InfraEvent) -> InfraEvent:
        """Detect platform and promote the resource to the typed subclass.

        Returns a new InfraEvent with the promoted resource.
        """
        resource = event.resource

        # 1. Explicit config override
        if self._override:
            promoted = self._promote_by_platform(resource, self._override)
            log.debug(
                "environment.detected",
                event_id=event.event_id,
                platform=self._override,
                source="config",
            )
            return event.model_copy(update={"resource": promoted})

        # 2. K8s detection (takes priority over AWS for EKS)
        extra = resource.extra
        if extra.get("k8s.pod.name") or extra.get("k8s.namespace.name"):
            promoted = _promote_k8s(resource)
            log.debug(
                "environment.detected",
                event_id=event.event_id,
                platform="k8s",
                source="attributes",
            )
            return event.model_copy(update={"resource": promoted})

        # 3. Docker detection
        if extra.get("container.runtime") == "docker" or extra.get("container.id"):
            promoted = _promote_docker(resource)
            log.debug(
                "environment.detected",
                event_id=event.event_id,
                platform="docker",
                source="attributes",
            )
            return event.model_copy(update={"resource": promoted})

        # 4. AWS detection
        if extra.get("cloud.provider") == "aws":
            promoted = _promote_aws(resource)
            log.debug(
                "environment.detected",
                event_id=event.event_id,
                platform="aws",
                source="attributes",
            )
            return event.model_copy(update={"resource": promoted})

        # 5. Default to K8s
        log.warning(
            "environment.default_fallback",
            event_id=event.event_id,
        )
        promoted = _promote_k8s(resource)
        return event.model_copy(update={"resource": promoted})

    def _promote_by_platform(self, resource: OTelResource, platform: str) -> OTelResource:
        if platform == "k8s":
            return _promote_k8s(resource)
        if platform == "docker":
            return _promote_docker(resource)
        if platform == "aws":
            return _promote_aws(resource)
        return resource
