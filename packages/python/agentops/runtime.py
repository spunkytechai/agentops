"""Policy-enforced synchronous tool executor."""
from collections.abc import Callable
from time import perf_counter
from typing import TypeVar
from uuid import uuid4

from .events import EventRecorder, InMemoryRecorder, RunEvent
from .policy import PolicyDeniedError, ToolPolicy

T = TypeVar("T")


class ToolExecutor:
    """Authorize before invocation and record metadata, never payloads.

    This is not a sandbox. Untrusted code needs process/container isolation and
    OS-level resource and network controls.
    """
    def __init__(self, policy: ToolPolicy, recorder: EventRecorder | None = None) -> None:
        self.policy = policy
        self.recorder = recorder if recorder is not None else InMemoryRecorder()

    def execute(self, tool_name: str, operation: Callable[[], T],
                *, run_id: str | None = None) -> T:
        decision = self.policy.evaluate(tool_name)
        if not decision.allowed:
            raise PolicyDeniedError(tool_name, decision.reason)

        execution_id = run_id or str(uuid4())
        self.recorder.record(RunEvent.create("tool.started", execution_id, tool_name))
        started = perf_counter()
        try:
            result = operation()
        except Exception as exc:
            self.recorder.record(RunEvent.create(
                "tool.failed", execution_id, tool_name,
                duration_ms=(perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
            ))
            raise
        self.recorder.record(RunEvent.create(
            "tool.succeeded", execution_id, tool_name,
            duration_ms=(perf_counter() - started) * 1000,
        ))
        return result
