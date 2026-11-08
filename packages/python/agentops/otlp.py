"""Dependency-free OTLP/HTTP JSON trace export."""
from __future__ import annotations

from collections import OrderedDict, deque
from datetime import datetime, timezone
import json
from typing import Callable, Mapping
from urllib.parse import urlsplit

from .events import RunEvent

HttpTransport = Callable[[str, Mapping[str, str], str], None]


class OtlpHttpSpanExporter:
    """Convert completed tool lifecycles to OTLP/HTTP JSON spans.

    Network I/O is injected by the host application. The exporter is synchronous;
    applications should call flush from a worker or shutdown hook, not in a hot
    execution path. Only allowlisted metadata is exported.
    """

    def __init__(
        self,
        endpoint: str,
        transport: HttpTransport,
        *,
        max_queue_size: int = 2048,
        max_batch_size: int = 512,
        max_retries: int = 2,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("endpoint must be an absolute HTTP or HTTPS URL")
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
               for v in (max_queue_size, max_batch_size)):
            raise ValueError("queue and batch sizes must be positive integers")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        self._url = endpoint.rstrip("/") + "/v1/traces"
        self._transport = transport
        self._max_queue_size = max_queue_size
        self._max_batch_size = min(max_batch_size, max_queue_size)
        self._max_retries = max_retries
        self._pending: OrderedDict[tuple[str, str], RunEvent] = OrderedDict()
        self._queue: deque[dict[str, object]] = deque()
        self.dropped_spans = 0

    def record(self, event: RunEvent) -> None:
        if event.trace_id is None or event.span_id is None:
            return
        key = (event.trace_id, event.span_id)
        if event.event_type == "tool.started":
            if len(self._pending) + len(self._queue) >= self._max_queue_size:
                self.dropped_spans += 1
                return
            self._pending[key] = event
            return
        started = self._pending.pop(key, None)
        if started is None:
            return
        if len(self._queue) >= self._max_queue_size:
            self.dropped_spans += 1
            return
        self._queue.append(self._span(started, event))

    @staticmethod
    def _unix_nano(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("event timestamps must be timezone-aware")
        utc = value.astimezone(timezone.utc)
        seconds = int(utc.timestamp())
        return str(seconds * 1_000_000_000 + utc.microsecond * 1_000)

    @staticmethod
    def _attribute(key: str, value: str | int | float | bool) -> dict[str, object]:
        field = "boolValue" if isinstance(value, bool) else (
            "intValue" if isinstance(value, int) else (
                "doubleValue" if isinstance(value, float) else "stringValue"
            )
        )
        return {"key": key, "value": {field: str(value) if field == "intValue" else value}}

    def _span(self, started: RunEvent, ended: RunEvent) -> dict[str, object]:
        success = ended.event_type == "tool.succeeded"
        attributes = [
            self._attribute("agentops.run_id", started.run_id),
            self._attribute("agentops.tool_name", started.tool_name),
            self._attribute("agentops.status", "ok" if success else "error"),
        ]
        if ended.duration_ms is not None:
            attributes.append(self._attribute("agentops.duration_ms", ended.duration_ms))
        if ended.error_type:
            attributes.append(self._attribute("error.type", ended.error_type))
        span: dict[str, object] = {
            "traceId": started.trace_id,
            "spanId": started.span_id,
            "name": started.tool_name,
            "kind": 1,
            "startTimeUnixNano": self._unix_nano(started.timestamp),
            "endTimeUnixNano": self._unix_nano(ended.timestamp),
            "attributes": attributes,
            "status": {"code": 1 if success else 2},
        }
        if started.parent_span_id:
            span["parentSpanId"] = started.parent_span_id
        return span

    def flush(self) -> int:
        exported = 0
        while self._queue:
            batch = [self._queue.popleft() for _ in range(min(len(self._queue), self._max_batch_size))]
            body = json.dumps({
                "resourceSpans": [{
                    "resource": {"attributes": []},
                    "scopeSpans": [{
                        "scope": {"name": "agentops", "version": "0.1.0"},
                        "spans": batch,
                    }],
                }],
            }, separators=(",", ":"))
            error: Exception | None = None
            for _ in range(self._max_retries + 1):
                try:
                    self._transport(self._url, {"Content-Type": "application/json"}, body)
                    error = None
                    break
                except Exception as exc:
                    error = exc
            if error is not None:
                self._queue.extendleft(reversed(batch))
                raise error
            exported += len(batch)
        return exported
