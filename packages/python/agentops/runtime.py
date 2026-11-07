"""Policy-enforced synchronous and asynchronous tool execution."""
import asyncio
import math
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import TypeVar
from uuid import uuid4

from .events import EventRecorder, InMemoryRecorder, RunEvent
from .policy import PolicyDeniedError, ToolPolicy

T = TypeVar("T")


class ToolExecutionTimeoutError(TimeoutError):
    """Raised when an authorized tool exceeds its configured execution timeout."""


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

    async def execute_async(
        self,
        tool_name: str,
        operation: Callable[[], Awaitable[T]],
        *,
        run_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> T:
        """Execute an async tool with optional timeout and task cancellation."""
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")

        decision = self.policy.evaluate(tool_name)
        if not decision.allowed:
            raise PolicyDeniedError(tool_name, decision.reason)

        execution_id = run_id or str(uuid4())
        self.recorder.record(RunEvent.create("tool.started", execution_id, tool_name))
        started = perf_counter()
        try:
            task = asyncio.ensure_future(operation())
            try:
                result = (
                    await task
                    if timeout_seconds is None
                    else await asyncio.wait_for(task, timeout=timeout_seconds)
                )
            except TimeoutError as exc:
                # Preserve a TimeoutError raised by the operation itself.
                if task.done() and not task.cancelled():
                    raise
                self.recorder.record(RunEvent.create(
                    "tool.failed", execution_id, tool_name,
                    duration_ms=(perf_counter() - started) * 1000,
                    error_type="ToolExecutionTimeoutError",
                ))
                raise ToolExecutionTimeoutError(
                    f"Tool {tool_name!r} exceeded {timeout_seconds} seconds"
                ) from exc
        except asyncio.CancelledError:
            self.recorder.record(RunEvent.create(
                "tool.failed", execution_id, tool_name,
                duration_ms=(perf_counter() - started) * 1000,
                error_type="CancelledError",
            ))
            raise
        except ToolExecutionTimeoutError:
            raise
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
