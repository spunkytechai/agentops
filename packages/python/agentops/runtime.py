"""Policy-enforced synchronous and asynchronous tool execution."""
import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from .approvals import ApprovalManager
from .events import EventRecorder, InMemoryRecorder, RunEvent, TraceContext
from .fingerprint import canonical_action_json
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

    def execute(
        self,
        tool_name: str,
        operation: Callable[[], T],
        *,
        run_id: str | None = None,
        principal_id: str | None = None,
        trace_context: TraceContext | None = None,
    ) -> T:
        decision = self.policy.evaluate(tool_name, principal_id=principal_id)
        if not decision.allowed:
            raise PolicyDeniedError(tool_name, decision.reason)

        execution_id = run_id or str(uuid4())
        context = trace_context or TraceContext.create()
        self.recorder.record(RunEvent.create("tool.started", execution_id, tool_name, trace_context=context))
        started = perf_counter()
        try:
            result = operation()
        except Exception as exc:
            self.recorder.record(RunEvent.create(
                "tool.failed", execution_id, tool_name,
                duration_ms=(perf_counter() - started) * 1000,
                error_type=type(exc).__name__, trace_context=context,
            ))
            raise
        self.recorder.record(RunEvent.create(
            "tool.succeeded", execution_id, tool_name,
            duration_ms=(perf_counter() - started) * 1000, trace_context=context,
        ))
        return result

    def execute_approved(
        self,
        tool_name: str,
        operation: Callable[[Mapping[str, Any]], T],
        *,
        principal_id: str,
        approval_manager: ApprovalManager,
        approval_request_id: str,
        action: Mapping[str, Any],
        run_id: str | None = None,
        trace_context: TraceContext | None = None,
    ) -> T:
        """Consume an action-bound approval immediately before invoking a tool."""
        decision = self.policy.evaluate(tool_name, principal_id=principal_id)
        if not decision.allowed:
            raise PolicyDeniedError(tool_name, decision.reason)
        approved_action = json.loads(canonical_action_json(action))
        approval_manager.consume(
            approval_request_id, principal_id, tool_name, action=approved_action
        )
        return self.execute(
            tool_name, lambda: operation(approved_action), run_id=run_id,
            principal_id=principal_id, trace_context=trace_context,
        )

    async def execute_async(
        self,
        tool_name: str,
        operation: Callable[[], Awaitable[T]],
        *,
        run_id: str | None = None,
        timeout_seconds: float | None = None,
        principal_id: str | None = None,
        trace_context: TraceContext | None = None,
    ) -> T:
        """Execute an async tool with optional timeout and task cancellation."""
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        decision = self.policy.evaluate(tool_name, principal_id=principal_id)
        if not decision.allowed:
            raise PolicyDeniedError(tool_name, decision.reason)

        execution_id = run_id or str(uuid4())
        context = trace_context or TraceContext.create()
        self.recorder.record(RunEvent.create("tool.started", execution_id, tool_name, trace_context=context))
        started = perf_counter()
        try:
            task = asyncio.ensure_future(operation())
            try:
                result = (
                    await task if timeout_seconds is None
                    else await asyncio.wait_for(task, timeout=timeout_seconds)
                )
            except asyncio.TimeoutError as exc:
                if task.done() and not task.cancelled():
                    raise
                self.recorder.record(RunEvent.create(
                    "tool.failed", execution_id, tool_name,
                    duration_ms=(perf_counter() - started) * 1000,
                    error_type="ToolExecutionTimeoutError", trace_context=context,
                ))
                raise ToolExecutionTimeoutError(
                    f"Tool {tool_name!r} exceeded {timeout_seconds} seconds"
                ) from exc
        except asyncio.CancelledError:
            self.recorder.record(RunEvent.create(
                "tool.failed", execution_id, tool_name,
                duration_ms=(perf_counter() - started) * 1000,
                error_type="CancelledError", trace_context=context,
            ))
            raise
        except ToolExecutionTimeoutError:
            raise
        except Exception as exc:
            self.recorder.record(RunEvent.create(
                "tool.failed", execution_id, tool_name,
                duration_ms=(perf_counter() - started) * 1000,
                error_type=type(exc).__name__, trace_context=context,
            ))
            raise
        self.recorder.record(RunEvent.create(
            "tool.succeeded", execution_id, tool_name,
            duration_ms=(perf_counter() - started) * 1000, trace_context=context,
        ))
        return result

    async def execute_async_approved(
        self,
        tool_name: str,
        operation: Callable[[Mapping[str, Any]], Awaitable[T]],
        *,
        principal_id: str,
        approval_manager: ApprovalManager,
        approval_request_id: str,
        action: Mapping[str, Any],
        run_id: str | None = None,
        timeout_seconds: float | None = None,
        trace_context: TraceContext | None = None,
    ) -> T:
        """Async equivalent of execute_approved with the same action binding."""
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        decision = self.policy.evaluate(tool_name, principal_id=principal_id)
        if not decision.allowed:
            raise PolicyDeniedError(tool_name, decision.reason)
        approved_action = json.loads(canonical_action_json(action))
        approval_manager.consume(
            approval_request_id, principal_id, tool_name, action=approved_action
        )
        return await self.execute_async(
            tool_name, lambda: operation(approved_action), run_id=run_id,
            timeout_seconds=timeout_seconds, principal_id=principal_id,
            trace_context=trace_context,
        )
