from dataclasses import replace
import json
import threading
import unittest
from datetime import datetime, timezone

from agentops import RunEvent
from agentops import OtlpHttpSpanExporter


class OtlpHttpSpanExporterTests(unittest.TestCase):
    def event(self, event_type, timestamp, **kwargs):
        run_id = kwargs.pop("run_id", "run-1")
        tool_name = kwargs.pop("tool_name", "search")
        return RunEvent(
            event_type=event_type,
            run_id=run_id,
            tool_name=tool_name,
            timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
            trace_id="1" * 32,
            span_id=kwargs.pop("span_id", "2" * 16),
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

    def test_rejects_collector_url_with_embedded_credentials(self):
        with self.assertRaises(ValueError):
            OtlpHttpSpanExporter(
                "https://user:password@collector:4318",
                lambda url, headers, body: None,
            )

    def test_drops_spans_with_oversized_exported_metadata(self):
        exporter = OtlpHttpSpanExporter(
            "http://collector:4318", lambda url, headers, body: None,
            max_attribute_bytes=8,
        )
        exporter.record(self.event(
            "tool.started", "2026-11-08T00:00:00", run_id="é" * 5
        ))
        exporter.record(self.event(
            "tool.succeeded", "2026-11-08T00:00:00.001",
            run_id="é" * 5, duration_ms=1,
        ))
        self.assertEqual(exporter.dropped_spans, 1)
        self.assertEqual(exporter.flush(), 0)

        exporter.record(self.event("tool.started", "2026-11-08T00:00:01"))
        exporter.record(self.event(
            "tool.failed", "2026-11-08T00:00:01.001",
            error_type="SensitiveErrorName",
        ))
        self.assertEqual(exporter.dropped_spans, 2)
        self.assertEqual(exporter.flush(), 0)

    def test_drops_events_with_unbounded_duration_metadata(self):
        exporter = OtlpHttpSpanExporter(
            "http://collector:4318", lambda url, headers, body: None
        )
        started = self.event("tool.started", "2026-11-08T00:00:00")
        exporter.record(started)
        ended = replace(
            self.event("tool.succeeded", "2026-11-08T00:00:00.001"),
            duration_ms=10 ** 1000,
        )
        exporter.record(ended)
        self.assertEqual(exporter.dropped_spans, 1)
        self.assertEqual(exporter.flush(), 0)

    def test_drops_events_with_invalid_trace_identifiers(self):
        exporter = OtlpHttpSpanExporter(
            "http://collector:4318", lambda url, headers, body: None
        )
        invalid = replace(
            self.event("tool.started", "2026-11-08T00:00:00"),
            trace_id="x" * 10_000,
        )
        exporter.record(invalid)
        self.assertEqual(exporter.dropped_spans, 1)
        self.assertEqual(exporter.flush(), 0)

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

    def test_concurrent_flushes_preserve_fifo_delivery(self):
        sent = []
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        second_done = threading.Event()
        results = []

        def transport(url, headers, body):
            span = json.loads(body)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
            run_id = next(
                item["value"]["stringValue"] for item in span["attributes"]
                if item["key"] == "agentops.run_id"
            )
            sent.append(run_id)
            if run_id == "first":
                first_started.set()
                if not release_first.wait(timeout=3):
                    raise TimeoutError("test did not release first transport")

        exporter = OtlpHttpSpanExporter(
            "http://collector:4318", transport, max_batch_size=1
        )
        for run_id, span_id, base in (
            ("first", "2" * 16, "2026-11-08T00:00:00"),
            ("second", "4" * 16, "2026-11-08T00:00:01"),
        ):
            exporter.record(self.event(
                "tool.started", base, run_id=run_id, span_id=span_id
            ))
            exporter.record(self.event(
                "tool.succeeded", base + ".001", run_id=run_id,
                span_id=span_id, duration_ms=1,
            ))

        first_thread = threading.Thread(target=lambda: results.append(exporter.flush()))
        def run_second_flush():
            second_started.set()
            results.append(exporter.flush())
            second_done.set()
        second_thread = threading.Thread(target=run_second_flush)

        first_thread.start()
        self.assertTrue(first_started.wait(timeout=2))
        second_thread.start()
        self.assertTrue(second_started.wait(timeout=2))
        try:
            self.assertFalse(second_done.wait(timeout=0.1))
            self.assertEqual(sent, ["first"])
        finally:
            release_first.set()
        first_thread.join(timeout=3)
        second_thread.join(timeout=3)
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertCountEqual(results, [2, 0])
        self.assertEqual(sent, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
