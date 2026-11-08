import json
import unittest
from datetime import datetime, timezone

from agentops import RunEvent
from agentops import OtlpHttpSpanExporter


class OtlpHttpSpanExporterTests(unittest.TestCase):
    def event(self, event_type, timestamp, **kwargs):
        return RunEvent(
            event_type=event_type,
            run_id="run-1",
            tool_name="search",
            timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
            trace_id="1" * 32,
            span_id="2" * 16,
            parent_span_id="3" * 16,
            **kwargs,
        )

    def test_exports_completed_lifecycle_as_otlp_json_without_payload_data(self):
        requests = []
        exporter = OtlpHttpSpanExporter(
            "http://collector:4318",
            lambda url, headers, body: requests.append((url, headers, json.loads(body))),
        )
        exporter.record(self.event("tool.started", "2026-11-08T00:00:00"))
        exporter.record(self.event(
            "tool.succeeded", "2026-11-08T00:00:00.125", duration_ms=125.0
        ))

        self.assertEqual(exporter.flush(), 1)
        url, headers, payload = requests[0]
        self.assertEqual(url, "http://collector:4318/v1/traces")
        self.assertEqual(headers["Content-Type"], "application/json")
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertEqual(span["traceId"], "1" * 32)
        self.assertEqual(span["spanId"], "2" * 16)
        self.assertEqual(span["parentSpanId"], "3" * 16)
        self.assertEqual(span["name"], "search")
        self.assertEqual(span["startTimeUnixNano"], "1794096000000000000")
        self.assertEqual(span["endTimeUnixNano"], "1794096000125000000")
        self.assertEqual(span["status"]["code"], 1)
        encoded = json.dumps(payload)
        self.assertNotIn("prompt", encoded)
        self.assertNotIn("arguments", encoded)
        self.assertNotIn("secret", encoded)

    def test_failed_export_retains_batch_for_retry_and_bounds_pending_spans(self):
        attempts = []
        def transport(url, headers, body):
            attempts.append(body)
            if len(attempts) == 1:
                raise OSError("collector unavailable")

        exporter = OtlpHttpSpanExporter(
            "http://collector:4318", transport, max_queue_size=1, max_retries=1
        )
        exporter.record(self.event("tool.started", "2026-11-08T00:00:00"))
        exporter.record(self.event("tool.succeeded", "2026-11-08T00:00:00.001", duration_ms=1))
        self.assertEqual(exporter.flush(), 1)
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
