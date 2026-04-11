## ADDED Requirements

### Requirement: Environment Detector promotes OTelResource to typed subclass
The `EnvironmentDetector` SHALL inspect an `InfraEvent`'s resource attributes and promote the base `OTelResource` to the appropriate typed subclass (`K8sResource`, `DockerResource`, or `AWSResource`). It MUST check attributes in the `OTelResource.extra` dict for platform-identifying keys.

#### Scenario: K8s detected from pod name attribute
- **WHEN** an InfraEvent has `k8s.pod.name` in `resource.extra`
- **THEN** the detector creates a `K8sResource` from the base resource, preserving all K8s fields (`k8s_namespace`, `k8s_pod_name`, `k8s_node_name`, `k8s_deployment_name`)
- **AND** returns a new InfraEvent with the typed resource

#### Scenario: K8s detected from namespace attribute
- **WHEN** an InfraEvent has `k8s.namespace.name` in `resource.extra` but no `k8s.pod.name`
- **THEN** the detector creates a `K8sResource` from the base resource

#### Scenario: Docker detected from container runtime
- **WHEN** an InfraEvent has `container.runtime` equal to `"docker"` in `resource.extra`
- **THEN** the detector creates a `DockerResource` with `container_runtime="docker"`, `container_id` from `container.id`, `container_name` from `container.name`, and `image_name` from `container.image.name`

#### Scenario: Docker detected from container ID
- **WHEN** an InfraEvent has `container.id` in `resource.extra` but no `container.runtime`
- **THEN** the detector creates a `DockerResource` with available container fields

#### Scenario: AWS detected from cloud provider
- **WHEN** an InfraEvent has `cloud.provider` equal to `"aws"` in `resource.extra`
- **THEN** the detector creates an `AWSResource` with `cloud_provider="aws"`, `cloud_region` from `cloud.region`, `instance_id` from `host.id`, and `aws_service` from `cloud.platform`

#### Scenario: EKS event has both K8s and AWS attributes
- **WHEN** an InfraEvent has both `k8s.pod.name` and `cloud.provider=aws`
- **THEN** K8s detection takes priority and the detector creates a `K8sResource`

### Requirement: OCTANTIS_PLATFORM env var overrides auto-detection
The Environment Detector MUST support an explicit platform override via the `OCTANTIS_PLATFORM` environment variable. When set, the detector MUST promote the resource to the corresponding subclass regardless of OTLP resource attributes.

#### Scenario: Explicit Docker override
- **WHEN** `OCTANTIS_PLATFORM` is set to `"docker"`
- **THEN** the detector creates a `DockerResource` regardless of OTLP attributes
- **AND** MUST NOT log a warning about attribute mismatch

#### Scenario: Explicit AWS override
- **WHEN** `OCTANTIS_PLATFORM` is set to `"aws"`
- **THEN** the detector creates an `AWSResource` regardless of OTLP attributes

#### Scenario: Explicit K8s override
- **WHEN** `OCTANTIS_PLATFORM` is set to `"k8s"`
- **THEN** the detector creates a `K8sResource` regardless of OTLP attributes

### Requirement: Default to K8s when no platform detected
When neither OTLP attributes nor `OCTANTIS_PLATFORM` identify a platform, the detector MUST default to `K8sResource` for backwards compatibility.

#### Scenario: No platform indicators present
- **WHEN** an InfraEvent has no K8s, Docker, or AWS attributes and `OCTANTIS_PLATFORM` is not set
- **THEN** the detector creates a `K8sResource` from available fields
- **AND** logs a warning: `"platform not detected, defaulting to k8s"`

### Requirement: Environment Detector preserves all resource data
When promoting a base `OTelResource` to a subclass, the detector MUST preserve all existing fields including `service_name`, `service_namespace`, `host_name`, and the full `extra` dict.

#### Scenario: All fields preserved during promotion
- **WHEN** a base OTelResource has `service_name="my-app"`, `host_name="node-1"`, and `extra={"custom.label": "value"}`
- **THEN** the promoted `K8sResource` retains `service_name`, `host_name`, and the full `extra` dict unchanged
