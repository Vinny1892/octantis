"""Kubernetes collector: fetches pod/node/deployment state from K8s API."""

import structlog
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from octantis.models.event import InfraEvent, KubernetesContext

log = structlog.get_logger(__name__)


class KubernetesCollector:
    def __init__(self, in_cluster: bool = False, kubeconfig: str | None = None) -> None:
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config(config_file=kubeconfig)
        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()

    async def collect(self, event: InfraEvent) -> KubernetesContext:
        """Fetch Kubernetes context for the given event."""
        ctx = KubernetesContext()
        ns = event.resource.k8s_namespace
        pod = event.resource.k8s_pod_name
        node = event.resource.k8s_node_name
        deployment = event.resource.k8s_deployment_name

        if ns and pod:
            self._enrich_pod(ctx, ns, pod)

        if node:
            self._enrich_node(ctx, node)

        if ns and deployment:
            self._enrich_deployment(ctx, ns, deployment)

        if ns and pod:
            self._enrich_events(ctx, ns, pod)

        return ctx

    def _enrich_pod(self, ctx: KubernetesContext, ns: str, pod: str) -> None:
        try:
            pod_obj = self._core.read_namespaced_pod(name=pod, namespace=ns)
            ctx.pod_phase = pod_obj.status.phase
            ctx.pod_conditions = [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                }
                for c in (pod_obj.status.conditions or [])
            ]
            restarts = sum(
                (cs.restart_count or 0) for cs in (pod_obj.status.container_statuses or [])
            )
            ctx.pod_restart_count = restarts
        except ApiException as exc:
            log.warning("k8s.pod_fetch_failed", ns=ns, pod=pod, status=exc.status)

    def _enrich_node(self, ctx: KubernetesContext, node: str) -> None:
        try:
            node_obj = self._core.read_node(name=node)
            conditions = node_obj.status.conditions or []
            ctx.node_conditions = [
                {"type": c.type, "status": c.status, "reason": c.reason} for c in conditions
            ]
            ctx.node_pressure = {
                c.type: c.status == "True"
                for c in conditions
                if c.type in ("MemoryPressure", "DiskPressure", "PIDPressure")
            }
        except ApiException as exc:
            log.warning("k8s.node_fetch_failed", node=node, status=exc.status)

    def _enrich_deployment(self, ctx: KubernetesContext, ns: str, deployment: str) -> None:
        try:
            dep = self._apps.read_namespaced_deployment(name=deployment, namespace=ns)
            ctx.deployment_available_replicas = dep.status.available_replicas or 0
            ctx.deployment_desired_replicas = dep.spec.replicas or 0
        except ApiException as exc:
            log.warning(
                "k8s.deployment_fetch_failed",
                ns=ns,
                deployment=deployment,
                status=exc.status,
            )

    def _enrich_events(self, ctx: KubernetesContext, ns: str, pod: str) -> None:
        try:
            events = self._core.list_namespaced_event(
                namespace=ns,
                field_selector=f"involvedObject.name={pod}",
            )
            ctx.recent_events = [
                {
                    "type": e.type,
                    "reason": e.reason,
                    "message": e.message,
                    "count": e.count,
                    "last_timestamp": str(e.last_timestamp),
                }
                for e in (events.items or [])[-10:]
            ]
        except ApiException as exc:
            log.warning("k8s.events_fetch_failed", ns=ns, pod=pod, status=exc.status)
