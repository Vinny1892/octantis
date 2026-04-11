"""OTLP payload parser — converts Protobuf and JSON payloads to InfraEvent."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue

from octantis.models.event import InfraEvent, LogRecord, MetricDataPoint, OTelResource

log = structlog.get_logger(__name__)

_RESOURCE_ATTR_MAP: dict[str, str] = {
    "service.name": "service_name",
    "service.namespace": "service_namespace",
    "host.name": "host_name",
}


def _any_value_to_python(av: AnyValue) -> Any:
    """Extract a Python value from an OTLP AnyValue."""
    kind = av.WhichOneof("value")
    if kind == "string_value":
        return av.string_value
    if kind == "int_value":
        return av.int_value
    if kind == "double_value":
        return av.double_value
    if kind == "bool_value":
        return av.bool_value
    if kind == "bytes_value":
        return av.bytes_value
    return str(av)


def _extract_resource(attributes: list[KeyValue]) -> OTelResource:
    """Map OTLP resource attributes to OTelResource."""
    known: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for kv in attributes:
        value = _any_value_to_python(kv.value)
        field = _RESOURCE_ATTR_MAP.get(kv.key)
        if field:
            known[field] = value
        extra[kv.key] = value

    return OTelResource(**known, extra=extra)


def _nano_to_datetime(time_unix_nano: int) -> datetime:
    """Convert OTLP nanosecond timestamp to datetime."""
    if time_unix_nano == 0:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(time_unix_nano / 1e9, tz=UTC)


_NODE_CPU_NORMALIZATION: set[str] = {"node_cpu_seconds_total"}


def _normalize_metric(name: str, value: float) -> float:
    """Normalize known Node Exporter counters to percentages."""
    if name in _NODE_CPU_NORMALIZATION:
        normalized = (value % 1.0) * 100.0
        normalized = min(normalized, 100.0)
        log.debug(
            "parser.counter_normalized",
            metric_name=name,
            raw_value=value,
            normalized_value=normalized,
        )
        return normalized
    return value


class OTLPParser:
    """Parses OTLP Protobuf and JSON payloads into InfraEvent."""

    def parse_metrics_proto(self, request: ExportMetricsServiceRequest) -> InfraEvent | None:
        """Parse an ExportMetricsServiceRequest Protobuf message."""
        try:
            return self._build_metrics_event(request)
        except Exception:
            return None

    def parse_logs_proto(self, request: ExportLogsServiceRequest) -> InfraEvent | None:
        """Parse an ExportLogsServiceRequest Protobuf message."""
        try:
            return self._build_logs_event(request)
        except Exception:
            return None

    def parse_metrics_json(self, data: dict[str, Any]) -> InfraEvent | None:
        """Parse an OTLP JSON metrics payload (resourceMetrics)."""
        try:
            request = ExportMetricsServiceRequest()
            from google.protobuf.json_format import ParseDict

            ParseDict(data, request)
            return self._build_metrics_event(request)
        except Exception:
            return None

    def parse_logs_json(self, data: dict[str, Any]) -> InfraEvent | None:
        """Parse an OTLP JSON logs payload (resourceLogs)."""
        try:
            request = ExportLogsServiceRequest()
            from google.protobuf.json_format import ParseDict

            ParseDict(data, request)
            return self._build_logs_event(request)
        except Exception:
            return None

    def _build_metrics_event(self, request: ExportMetricsServiceRequest) -> InfraEvent:
        """Build an InfraEvent from a metrics request."""
        resource = OTelResource()
        metrics: list[MetricDataPoint] = []
        raw_payload: dict[str, Any] = {}

        for rm in request.resource_metrics:
            resource = _extract_resource(list(rm.resource.attributes))
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    name = m.name
                    unit = m.unit or None
                    data_points = []
                    if m.HasField("gauge"):
                        data_points = list(m.gauge.data_points)
                    elif m.HasField("sum"):
                        data_points = list(m.sum.data_points)

                    for dp in data_points:
                        value = dp.as_double if dp.as_double != 0.0 else float(dp.as_int)
                        value = _normalize_metric(name, value)
                        metrics.append(
                            MetricDataPoint(
                                name=name,
                                value=value,
                                unit=unit,
                                timestamp=_nano_to_datetime(dp.time_unix_nano),
                            )
                        )

        event_type = "metric" if metrics else "unknown"
        try:
            from google.protobuf.json_format import MessageToDict

            raw_payload = MessageToDict(request)
        except Exception:
            pass

        return InfraEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source=resource.service_name or "unknown",
            resource=resource,
            metrics=metrics,
            logs=[],
            raw_payload=raw_payload,
        )

    def _build_logs_event(self, request: ExportLogsServiceRequest) -> InfraEvent:
        """Build an InfraEvent from a logs request."""
        resource = OTelResource()
        logs: list[LogRecord] = []
        raw_payload: dict[str, Any] = {}

        for rl in request.resource_logs:
            resource = _extract_resource(list(rl.resource.attributes))
            for sl in rl.scope_logs:
                for lr in sl.log_records:
                    body = ""
                    if lr.body.WhichOneof("value") == "string_value":
                        body = lr.body.string_value
                    else:
                        body = str(lr.body)

                    logs.append(
                        LogRecord(
                            body=body,
                            severity_text=lr.severity_text or None,
                            severity_number=lr.severity_number or None,
                            timestamp=_nano_to_datetime(lr.time_unix_nano),
                        )
                    )

        event_type = "log" if logs else "unknown"
        try:
            from google.protobuf.json_format import MessageToDict

            raw_payload = MessageToDict(request)
        except Exception:
            pass

        return InfraEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source=resource.service_name or "unknown",
            resource=resource,
            metrics=[],
            logs=logs,
            raw_payload=raw_payload,
        )
