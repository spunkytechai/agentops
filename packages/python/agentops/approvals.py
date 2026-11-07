"""In-memory human approval workflow for consequential tool actions."""
from dataclasses import dataclass
import math
from collections.abc import Mapping
from threading import RLock
from time import time
from typing import Any, Callable
from uuid import uuid4

from .fingerprint import action_fingerprint


class ApprovalRequiredError(PermissionError):
    """Raised when a valid, unconsumed approval is not available."""


class ApprovalDeniedError(ApprovalRequiredError):
    """Raised when a human explicitly denied an approval request."""


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    request_id: str
    principal_id: str
    tool_name: str
    summary: str
    status: str
    expires_at: float
    approver_id: str | None = None
    reason: str | None = None
    action_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    request_id: str
    principal_id: str
    tool_name: str
    approver_id: str
    action_fingerprint: str | None = None


@dataclass(slots=True)
class _ApprovalRecord:
    request: ApprovalRequest


class ApprovalManager:
    """Process-local, one-time approval state machine.

    Authentication and authorization of approvers belong to the host
    application. Persist this workflow in a durable, transactional store when
    approvals must survive restarts or coordinate multiple workers.
    """

    def __init__(self, *, clock: Callable[[], float] = time) -> None:
        self._clock = clock
        self._records: dict[str, _ApprovalRecord] = {}
        self._lock = RLock()

    def request(
        self,
        principal_id: str,
        tool_name: str,
        summary: str,
        *,
        ttl_seconds: float = 300,
        action: Mapping[str, Any] | None = None,
    ) -> ApprovalRequest:
        for value, name in (
            (principal_id, "principal_id"),
            (tool_name, "tool_name"),
            (summary, "summary"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or not math.isfinite(ttl_seconds)
            or ttl_seconds <= 0
        ):
            raise ValueError("ttl_seconds must be a positive finite number")

        fingerprint = action_fingerprint(action) if action is not None else None
        request = ApprovalRequest(
            request_id=str(uuid4()),
            principal_id=principal_id,
            tool_name=tool_name,
            summary=summary,
            status="pending",
            expires_at=self._clock() + ttl_seconds,
            action_fingerprint=fingerprint,
        )
        with self._lock:
            self._records[request.request_id] = _ApprovalRecord(request)
        return request

    def get(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            record = self._get_record(request_id)
            return self._expire_if_needed(record).request

    def approve(self, request_id: str, *, approver_id: str) -> ApprovalRequest:
        self._validate_identity(approver_id, "approver_id")
        with self._lock:
            record = self._expire_if_needed(self._get_record(request_id))
            if record.request.status != "pending":
                raise ApprovalDeniedError(
                    f"Approval request {request_id!r} is {record.request.status}"
                )
            record.request = self._replace(
                record.request, status="approved", approver_id=approver_id
            )
            return record.request

    def deny(
        self, request_id: str, *, approver_id: str, reason: str
    ) -> ApprovalRequest:
        self._validate_identity(approver_id, "approver_id")
        self._validate_identity(reason, "reason")
        with self._lock:
            record = self._expire_if_needed(self._get_record(request_id))
            if record.request.status != "pending":
                raise ApprovalDeniedError(
                    f"Approval request {request_id!r} is {record.request.status}"
                )
            record.request = self._replace(
                record.request, status="denied", approver_id=approver_id, reason=reason
            )
            return record.request

    def consume(
        self,
        request_id: str,
        principal_id: str,
        tool_name: str,
        *,
        action: Mapping[str, Any] | None = None,
    ) -> ApprovalGrant:
        with self._lock:
            record = self._expire_if_needed(self._get_record(request_id))
            request = record.request
            if request.principal_id != principal_id or request.tool_name != tool_name:
                raise ApprovalRequiredError("Approval does not match this principal and tool")
            if request.status == "denied":
                raise ApprovalDeniedError(f"Approval request {request_id!r} was denied")
            if request.status != "approved" or request.approver_id is None:
                raise ApprovalRequiredError(
                    f"Approval request {request_id!r} is {request.status}"
                )
            supplied_fingerprint = action_fingerprint(action) if action is not None else None
            if supplied_fingerprint != request.action_fingerprint:
                raise ApprovalRequiredError("Approval does not match the canonical action")
            record.request = self._replace(request, status="consumed")
            return ApprovalGrant(
                request_id=request.request_id,
                principal_id=request.principal_id,
                tool_name=request.tool_name,
                approver_id=request.approver_id,
                action_fingerprint=request.action_fingerprint,
            )

    def _get_record(self, request_id: str) -> _ApprovalRecord:
        record = self._records.get(request_id)
        if record is None:
            raise ApprovalRequiredError(f"Unknown approval request {request_id!r}")
        return record

    def _expire_if_needed(self, record: _ApprovalRecord) -> _ApprovalRecord:
        if record.request.status in ("pending", "approved") and self._clock() >= record.request.expires_at:
            record.request = self._replace(record.request, status="expired")
        return record

    @staticmethod
    def _replace(request: ApprovalRequest, **changes: object) -> ApprovalRequest:
        values = {
            "request_id": request.request_id,
            "principal_id": request.principal_id,
            "tool_name": request.tool_name,
            "summary": request.summary,
            "status": request.status,
            "expires_at": request.expires_at,
            "approver_id": request.approver_id,
            "reason": request.reason,
            "action_fingerprint": request.action_fingerprint,
        }
        values.update(changes)
        return ApprovalRequest(**values)

    @staticmethod
    def _validate_identity(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
