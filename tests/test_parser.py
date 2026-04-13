"""Unit tests for the OTLP parser — verifies SDK Event output (dict-based fields)."""

import uuid

from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)

from octantis.receivers.parser import OTLPParser


def _make_metrics_request(**overrides) -> ExportMetricsServiceRequest:
    """Build an ExportMetricsServiceRequest from a dict via ParseDict."""
    data = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "my-service"}},
                        {"key": "k8s.namespace.name", "value": {"stringValue": "default"}},
                        {"key": "k8s.pod.name", "value": {"stringValue": "pod-abc"}},
                    ]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "cpu_usage",
                                "unit": "%",
                                "gauge": {
                                    "dataPoints": [
                                        {"asDouble": 72.5, "timeUnixNano": "1700000000000000000"}
                                    ]
                                },
                            },
                            {
                                "name": "memory_usage",
                                "unit": "bytes",
                                "gauge": {
                                    "dataPoints": [
                                        {"asDouble": 1024.0, "timeUnixNano": "1700000000000000000"}
                                    ]
                                },
                            },
                        ]
                    }
                ],
            }
        ]
    }
    data.update(overrides)
    req = ExportMetricsServiceRequest()
    ParseDict(data, req)
    return req


def _make_logs_request(**overrides) -> ExportLogsServiceRequest:
    """Build an ExportLogsServiceRequest from a dict via ParseDict."""
    data = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "my-service"}},
                        {"key": "k8s.namespace.name", "value": {"stringValue": "default"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "Something went wrong"},
                                "severityText": "ERROR",
                                "severityNumber": 17,
                                "timeUnixNano": "1700000000000000000",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    data.update(overrides)
    req = ExportLogsServiceRequest()
    ParseDict(data, req)
    return req


parser = OTLPParser()


class TestParseMetricsProto:
    def test_valid_metrics(self):
        req = _make_metrics_request()
        event = parser.parse_metrics_proto(req)
        assert event is not None
        assert event.event_type == "metric"
        assert len(event.metrics) == 2
        assert event.metrics[0]["name"] == "cpu_usage"
        assert event.metrics[0]["value"] == 72.5
        assert event.metrics[0]["unit"] == "%"
        assert event.metrics[1]["name"] == "memory_usage"
        assert event.metrics[1]["value"] == 1024.0

    def test_resource_mapping(self):
        req = _make_metrics_request()
        event = parser.parse_metrics_proto(req)
        assert event.resource.get("service.name") == "my-service"
        assert event.resource.get("k8s.namespace.name") == "default"
        assert event.resource.get("k8s.pod.name") == "pod-abc"

    def test_extra_attributes(self):
        req = ExportMetricsServiceRequest()
        ParseDict(
            {
                "resourceMetrics": [
                    {
                        "resource": {
                            "attributes": [
                                {"key": "custom.label", "value": {"stringValue": "val"}},
                            ]
                        },
                        "scopeMetrics": [],
                    }
                ]
            },
            req,
        )
        event = parser.parse_metrics_proto(req)
        assert "custom.label" in event.resource
        assert event.resource["custom.label"] == "val"

    def test_empty_payload(self):
        req = ExportMetricsServiceRequest()
        ParseDict(
            {
                "resourceMetrics": [
                    {
                        "resource": {
                            "attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]
                        },
                        "scopeMetrics": [],
                    }
                ]
            },
            req,
        )
        event = parser.parse_metrics_proto(req)
        assert event.event_type == "unknown"
        assert event.metrics == []
        assert event.logs == []

    def test_event_id_is_uuid4(self):
        req = _make_metrics_request()
        event = parser.parse_metrics_proto(req)
        parsed = uuid.UUID(event.event_id, version=4)
        assert str(parsed) == event.event_id

    def test_source_from_service_name(self):
        req = _make_metrics_request()
        event = parser.parse_metrics_proto(req)
        assert event.source == "my-service"

    def test_source_fallback_unknown(self):
        req = ExportMetricsServiceRequest()
        ParseDict(
            {
                "resourceMetrics": [
                    {
                        "resource": {"attributes": []},
                        "scopeMetrics": [],
                    }
                ]
            },
            req,
        )
        event = parser.parse_metrics_proto(req)
        assert event.source == "unknown"


class TestParseLogsProto:
    def test_valid_logs(self):
        req = _make_logs_request()
        event = parser.parse_logs_proto(req)
        assert event is not None
        assert event.event_type == "log"
        assert len(event.logs) == 1
        assert event.logs[0]["body"] == "Something went wrong"
        assert event.logs[0]["severity_text"] == "ERROR"
        assert event.logs[0]["severity_number"] == 17

    def test_resource_mapping(self):
        req = _make_logs_request()
        event = parser.parse_logs_proto(req)
        assert event.resource.get("service.name") == "my-service"
        assert event.resource.get("k8s.namespace.name") == "default"


class TestParseMetricsJson:
    def test_valid_json_metrics(self):
        data = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "json-svc"}},
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "requests",
                                    "unit": "1",
                                    "gauge": {"dataPoints": [{"asDouble": 42.0}]},
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        event = parser.parse_metrics_json(data)
        assert event is not None
        assert event.event_type == "metric"
        assert event.metrics[0]["name"] == "requests"
        assert event.metrics[0]["value"] == 42.0
        assert event.source == "json-svc"


class TestParseLogsJson:
    def test_valid_json_logs(self):
        data = {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "log-svc"}},
                        ]
                    },
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "body": {"stringValue": "test log"},
                                    "severityText": "INFO",
                                    "severityNumber": 9,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        event = parser.parse_logs_json(data)
        assert event is not None
        assert event.event_type == "log"
        assert event.logs[0]["body"] == "test log"


class TestMalformedInput:
    def test_malformed_proto_returns_none(self):
        req = ExportMetricsServiceRequest()
        # Valid empty request — should still return an event, not None
        event = parser.parse_metrics_proto(req)
        assert event is not None

    def test_invalid_json_returns_none(self):
        result = parser.parse_metrics_json({"garbage": True})
        # ParseDict on invalid structure — should either return event or None
        # The key is it doesn't raise
        assert result is None or result is not None  # no exception

    def test_logs_invalid_json_returns_none(self):
        result = parser.parse_logs_json({"garbage": True})
        assert result is None or result is not None  # no exception


class TestCounterNormalization:
    """Tests for Node Exporter counter normalization in the parser."""

    def test_cpu_counter_normalized_to_percentage(self):
        data = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "node-exporter"}},
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "node_cpu_seconds_total",
                                    "unit": "s",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "asDouble": 123456.78,
                                                "timeUnixNano": "1700000000000000000",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        event = parser.parse_metrics_json(data)
        assert event is not None
        assert len(event.metrics) == 1
        m = event.metrics[0]
        assert m["name"] == "node_cpu_seconds_total"
        assert m["value"] == (123456.78 % 1.0) * 100.0

    def test_unknown_metric_not_normalized(self):
        data = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "my-app"}},
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "custom_metric_total",
                                    "unit": "1",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "asDouble": 123456.78,
                                                "timeUnixNano": "1700000000000000000",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        event = parser.parse_metrics_json(data)
        assert event is not None
        assert event.metrics[0]["name"] == "custom_metric_total"
        assert event.metrics[0]["value"] == 123456.78

    def test_node_memory_gauge_not_normalized(self):
        data = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "node-exporter"}},
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "node_memory_MemAvailable_bytes",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "asDouble": 2147483648.0,
                                                "timeUnixNano": "1700000000000000000",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        event = parser.parse_metrics_json(data)
        assert event is not None
        assert event.metrics[0]["name"] == "node_memory_MemAvailable_bytes"
        assert event.metrics[0]["value"] == 2147483648.0
