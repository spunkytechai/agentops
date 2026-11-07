"""Structured execution events and in-memory recording."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

EventType = Literal["tool.started", "tool.succeeded", "tool.failed"]


@dataclass(frozen=True, slots=True)
class RunEvent:
    """Lifecycle metadata; prompts, arguments, results, and secrets are excluded."""
    event_type: EventType
    run_id: str
    tool_name: str
    timestamp: datetime
    duration_ms: float | None = None
    error_type: str | None = None

    @classmethod
    def create(cls, event_type: EventType, run_id: str, tool_name: str,
               *, duration_ms: float | None = None,
               error_type: str | None = None) -> "RunEvent":
        return cls(event_type, run_id, tool_name, datetime.now(timezone.utc),
                   duration_ms, error_type)


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
