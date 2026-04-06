"""Shared OTLP test payloads for fixtures and integration tests."""

import json
from pathlib import Path

from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)

METRICS_JSON = {
    "resourceMetrics": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "k8s-app"}},
                    {"key": "k8s.namespace.name", "value": {"stringValue": "production"}},
                    {"key": "k8s.pod.name", "value": {"stringValue": "k8s-app-7b8f9c-x2k"}},
                    {"key": "k8s.node.name", "value": {"stringValue": "node-1"}},
                ]
            },
            "scopeMetrics": [
                {
                    "metrics": [
                        {
                            "name": "container_cpu_usage_seconds_total",
                            "unit": "s",
                            "gauge": {
                                "dataPoints": [
                                    {"asDouble": 85.3, "timeUnixNano": "1700000000000000000"}
                                ]
                            },
                        },
                        {
                            "name": "container_memory_working_set_bytes",
                            "unit": "By",
                            "gauge": {
                                "dataPoints": [
                                    {"asDouble": 524288000.0, "timeUnixNano": "1700000000000000000"}
                                ]
                            },
                        },
                        {
                            "name": "kube_pod_container_status_restarts_total",
                            "unit": "1",
                            "sum": {
                                "dataPoints": [
                                    {"asInt": "3", "timeUnixNano": "1700000000000000000"}
                                ],
                                "isMonotonic": True,
                            },
                        },
                    ]
                }
            ],
        }
    ]
}

LOGS_JSON = {
    "resourceLogs": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "k8s-app"}},
                    {"key": "k8s.namespace.name", "value": {"stringValue": "production"}},
                    {"key": "k8s.pod.name", "value": {"stringValue": "k8s-app-7b8f9c-x2k"}},
                ]
            },
            "scopeLogs": [
                {
                    "logRecords": [
                        {
                            "body": {"stringValue": "OOMKilled: container exceeded memory limit"},
                            "severityText": "ERROR",
                            "severityNumber": 17,
                            "timeUnixNano": "1700000000000000000",
                        },
                        {
                            "body": {"stringValue": "Container restarting after crash"},
                            "severityText": "WARNING",
                            "severityNumber": 13,
                            "timeUnixNano": "1700000001000000000",
                        },
                    ]
                }
            ],
        }
    ]
}


def metrics_proto() -> ExportMetricsServiceRequest:
    req = ExportMetricsServiceRequest()
    ParseDict(METRICS_JSON, req)
    return req


def logs_proto() -> ExportLogsServiceRequest:
    req = ExportLogsServiceRequest()
    ParseDict(LOGS_JSON, req)
    return req


def generate_fixture_files():
    """Generate serialized fixture files (run once to create them)."""
    fixtures_dir = Path(__file__).parent

    # Protobuf
    (fixtures_dir / "otlp_metrics.pb").write_bytes(metrics_proto().SerializeToString())
    (fixtures_dir / "otlp_logs.pb").write_bytes(logs_proto().SerializeToString())

    # JSON
    (fixtures_dir / "otlp_metrics.json").write_text(json.dumps(METRICS_JSON, indent=2))
    (fixtures_dir / "otlp_logs.json").write_text(json.dumps(LOGS_JSON, indent=2))


if __name__ == "__main__":
    generate_fixture_files()
    print("Fixtures generated.")
