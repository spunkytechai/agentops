"""In-memory human approval workflow for consequential tool actions."""
from dataclasses import dataclass
import math
from threading import RLock
from time import time
from typing import Callable
from uuid import uuid4


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


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    request_id: str
    principal_id: str
    tool_name: str
    approver_id: str


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

        request = ApprovalRequest(
            request_id=str(uuid4()),
            principal_id=principal_id,
            tool_name=tool_name,
            summary=summary,
            status="pending",
            expires_at=self._clock() + ttl_seconds,
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
        self, request_id: str, principal_id: str, tool_name: str
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
            record.request = self._replace(request, status="consumed")
            return ApprovalGrant(
                request_id=request.request_id,
                principal_id=request.principal_id,
                tool_name=request.tool_name,
                approver_id=request.approver_id,
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
        }
        values.update(changes)
        return ApprovalRequest(**values)

    @staticmethod
    def _validate_identity(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
