"""Structured execution events and W3C trace-context propagation."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import secrets
from typing import Literal, Protocol

EventType = Literal["tool.started", "tool.succeeded", "tool.failed"]
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True, slots=True)
class TraceContext:
    """W3C Trace Context identifiers; propagation is explicit and provider-neutral."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.trace_id, str) or not _TRACE_ID.fullmatch(self.trace_id) or self.trace_id == "0" * 32:
            raise ValueError("trace_id must be 32 lowercase hexadecimal characters and non-zero")
        if not isinstance(self.span_id, str) or not _SPAN_ID.fullmatch(self.span_id) or self.span_id == "0" * 16:
            raise ValueError("span_id must be 16 lowercase hexadecimal characters and non-zero")
        if self.parent_span_id is not None and (
            not isinstance(self.parent_span_id, str)
            or not _SPAN_ID.fullmatch(self.parent_span_id)
            or self.parent_span_id == "0" * 16
        ):
            raise ValueError("parent_span_id must be 16 lowercase hexadecimal characters and non-zero")
        if self.parent_span_id == self.span_id:
            raise ValueError("parent_span_id must differ from span_id")

    @classmethod
    def create(cls, parent: "TraceContext | None" = None) -> "TraceContext":
        return cls(
            trace_id=parent.trace_id if parent else secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            parent_span_id=parent.span_id if parent else None,
        )


@dataclass(frozen=True, slots=True)
class RunEvent:
    """Lifecycle metadata; prompts, arguments, results, and secrets are excluded."""
    event_type: EventType
    run_id: str
    tool_name: str
    timestamp: datetime
    duration_ms: float | None = None
    error_type: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None

    @classmethod
    def create(cls, event_type: EventType, run_id: str, tool_name: str,
               *, duration_ms: float | None = None,
               error_type: str | None = None,
               trace_context: TraceContext | None = None) -> "RunEvent":
        return cls(
            event_type, run_id, tool_name, datetime.now(timezone.utc),
            duration_ms, error_type,
            trace_context.trace_id if trace_context else None,
            trace_context.span_id if trace_context else None,
            trace_context.parent_span_id if trace_context else None,
        )


class EventRecorder(Protocol):
    def record(self, event: RunEvent) -> None: ...


class InMemoryRecorder:
    """Recorder for tests and local development."""
    def __init__(self) -> None:
        self._events: list[RunEvent] = []

    def record(self, event: RunEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> tuple[RunEvent, ...]:
        return tuple(self._events)

    def clear(self) -> None:
        self._events.clear()
