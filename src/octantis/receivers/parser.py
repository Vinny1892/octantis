# SPDX-License-Identifier: AGPL-3.0-or-later
"""OTLP payload parser — converts Protobuf and JSON payloads to SDK Event.

All protobuf imports are deferred inside methods so this module is importable
without triggering opentelemetry-proto side effects at import time.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

import structlog
from octantis_plugin_sdk import Event as SDKEvent

log = structlog.get_logger(__name__)

_RESOURCE_ATTR_MAP: dict[str, str] = {
    "service.name": "service_name",
    "service.namespace": "service_namespace",
    "host.name": "host_name",
}


def _any_value_to_python(av: Any) -> Any:
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


def _extract_resource_dict(attributes: Any) -> dict[str, Any]:
    """Map OTLP resource attributes to a flat dict (all keys preserved)."""
    result: dict[str, Any] = {}
    for kv in attributes:
        result[kv.key] = _any_value_to_python(kv.value)
    return result


def _nano_to_iso(time_unix_nano: int) -> str:
    """Convert OTLP nanosecond timestamp to ISO 8601 string."""
    from datetime import UTC, datetime

    if time_unix_nano == 0:
        return datetime.now(tz=UTC).isoformat()
    return datetime.fromtimestamp(time_unix_nano / 1e9, tz=UTC).isoformat()


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
    """Parses OTLP Protobuf and JSON payloads into SDK Event dicts."""

    def parse_metrics_proto(self, request: Any) -> SDKEvent | None:
        """Parse an ExportMetricsServiceRequest Protobuf message."""
        try:
            return self._build_metrics_event(request)
        except Exception:
            return None

    def parse_logs_proto(self, request: Any) -> SDKEvent | None:
        """Parse an ExportLogsServiceRequest Protobuf message."""
        try:
            return self._build_logs_event(request)
        except Exception:
            return None

    def parse_metrics_json(self, data: dict[str, Any]) -> SDKEvent | None:
        """Parse an OTLP JSON metrics payload (resourceMetrics)."""
        try:
            from google.protobuf.json_format import ParseDict
            from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
                ExportMetricsServiceRequest,
            )

            request = ExportMetricsServiceRequest()
            ParseDict(data, request)
            return self._build_metrics_event(request)
        except Exception:
            return None

    def parse_logs_json(self, data: dict[str, Any]) -> SDKEvent | None:
        """Parse an OTLP JSON logs payload (resourceLogs)."""
        try:
            from google.protobuf.json_format import ParseDict
            from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
                ExportLogsServiceRequest,
            )

            request = ExportLogsServiceRequest()
            ParseDict(data, request)
            return self._build_logs_event(request)
        except Exception:
            return None

    def _build_metrics_event(self, request: Any) -> SDKEvent:
        """Build an SDK Event from a metrics request."""
        from google.protobuf.json_format import MessageToDict

        resource_dict: dict[str, Any] = {}
        metrics: list[dict[str, Any]] = []
        raw_payload: dict[str, Any] = {}

        for rm in request.resource_metrics:
            resource_dict = _extract_resource_dict(list(rm.resource.attributes))
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
                            {
                                "name": name,
                                "value": value,
                                "unit": unit,
                                "timestamp": _nano_to_iso(dp.time_unix_nano),
                            }
                        )

        event_type = "metric" if metrics else "unknown"
        with contextlib.suppress(Exception):
            raw_payload = MessageToDict(request)

        return SDKEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source=resource_dict.get("service.name") or "unknown",
            resource=resource_dict,
            metrics=metrics,
            logs=[],
            raw_payload=raw_payload,
        )

    def _build_logs_event(self, request: Any) -> SDKEvent:
        """Build an SDK Event from a logs request."""
        from google.protobuf.json_format import MessageToDict

        resource_dict: dict[str, Any] = {}
        logs: list[dict[str, Any]] = []
        raw_payload: dict[str, Any] = {}

        for rl in request.resource_logs:
            resource_dict = _extract_resource_dict(list(rl.resource.attributes))
            for sl in rl.scope_logs:
                for lr in sl.log_records:
                    body = ""
                    if lr.body.WhichOneof("value") == "string_value":
                        body = lr.body.string_value
                    else:
                        body = str(lr.body)

                    logs.append(
                        {
                            "body": body,
                            "severity_text": lr.severity_text or None,
                            "severity_number": lr.severity_number or None,
                            "timestamp": _nano_to_iso(lr.time_unix_nano),
                        }
                    )

        event_type = "log" if logs else "unknown"
        with contextlib.suppress(Exception):
            raw_payload = MessageToDict(request)

        return SDKEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source=resource_dict.get("service.name") or "unknown",
            resource=resource_dict,
            metrics=[],
            logs=logs,
            raw_payload=raw_payload,
        )
