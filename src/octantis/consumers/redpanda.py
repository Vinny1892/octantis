"""Redpanda/Kafka consumer using aiokafka."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from octantis.config import RedpandaSettings
from octantis.models.event import InfraEvent, LogRecord, MetricDataPoint, OTelResource

log = structlog.get_logger(__name__)


def _parse_otel_message(raw: dict[str, Any]) -> InfraEvent:
    """Convert an OTel Collector JSON export to InfraEvent.

    Supports both metric and log payloads exported by OTel Collector
    in JSON format (otlp/json).
    """
    resource_attrs: dict[str, Any] = {}
    for attr in raw.get("resourceMetrics", [{}])[0].get("resource", {}).get("attributes", []):
        resource_attrs[attr["key"]] = attr.get("value", {}).get("stringValue", "")

    # Also check resourceLogs
    if not resource_attrs:
        for attr in raw.get("resourceLogs", [{}])[0].get("resource", {}).get("attributes", []):
            resource_attrs[attr["key"]] = attr.get("value", {}).get("stringValue", "")

    resource = OTelResource(
        service_name=resource_attrs.get("service.name"),
        service_namespace=resource_attrs.get("service.namespace"),
        k8s_namespace=resource_attrs.get("k8s.namespace.name"),
        k8s_pod_name=resource_attrs.get("k8s.pod.name"),
        k8s_node_name=resource_attrs.get("k8s.node.name"),
        k8s_deployment_name=resource_attrs.get("k8s.deployment.name"),
        extra=resource_attrs,
    )

    metrics: list[MetricDataPoint] = []
    for rm in raw.get("resourceMetrics", []):
        for sm in rm.get("scopeMetrics", []):
            for m in sm.get("metrics", []):
                name = m.get("name", "")
                unit = m.get("unit", "")
                for dp in (
                    m.get("gauge", {}).get("dataPoints", [])
                    + m.get("sum", {}).get("dataPoints", [])
                ):
                    value = dp.get("asDouble") or dp.get("asInt", 0)
                    metrics.append(MetricDataPoint(name=name, value=float(value), unit=unit))

    logs: list[LogRecord] = []
    for rl in raw.get("resourceLogs", []):
        for sl in rl.get("scopeLogs", []):
            for lr in sl.get("logRecords", []):
                logs.append(
                    LogRecord(
                        body=lr.get("body", {}).get("stringValue", ""),
                        severity_text=lr.get("severityText"),
                        severity_number=lr.get("severityNumber"),
                    )
                )

    event_type = "metric" if metrics else ("log" if logs else "unknown")

    return InfraEvent(
        event_id=raw.get("event_id", str(uuid.uuid4())),
        event_type=event_type,
        source=resource.service_name or "unknown",
        resource=resource,
        metrics=metrics,
        logs=logs,
        raw_payload=raw,
    )


class RedpandaConsumer:
    """Async Redpanda/Kafka consumer that yields InfraEvent objects."""

    def __init__(self, config: RedpandaSettings) -> None:
        self._config = config
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        kwargs: dict[str, Any] = {
            "bootstrap_servers": self._config.broker_list,
            "group_id": self._config.group_id,
            "auto_offset_reset": "latest",
            "enable_auto_commit": True,
            "value_deserializer": lambda v: json.loads(v.decode("utf-8")),
        }

        if self._config.security_protocol != "PLAINTEXT":
            kwargs["security_protocol"] = self._config.security_protocol
        if self._config.sasl_mechanism:
            kwargs["sasl_mechanism"] = self._config.sasl_mechanism
            kwargs["sasl_plain_username"] = self._config.sasl_username
            kwargs["sasl_plain_password"] = self._config.sasl_password

        self._consumer = AIOKafkaConsumer(self._config.topic, **kwargs)
        await self._consumer.start()
        log.info(
            "redpanda.consumer.started",
            topic=self._config.topic,
            brokers=self._config.brokers,
        )

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            log.info("redpanda.consumer.stopped")

    async def events(self) -> AsyncIterator[InfraEvent]:
        """Yield parsed InfraEvent objects from the topic."""
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        async for msg in self._consumer:
            try:
                event = _parse_otel_message(msg.value)
                log.debug(
                    "redpanda.message.received",
                    event_id=event.event_id,
                    partition=msg.partition,
                    offset=msg.offset,
                )
                yield event
            except Exception as exc:
                log.error(
                    "redpanda.message.parse_error",
                    error=str(exc),
                    raw=str(msg.value)[:200],
                )
