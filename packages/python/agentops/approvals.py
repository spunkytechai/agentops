"""Human approval workflow with pluggable, transactional storage."""
from dataclasses import dataclass
import math
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Callable, Protocol
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


class ApprovalStore(Protocol):
    """Storage contract; consume must atomically compare and mark one grant consumed."""

    def create(self, request: ApprovalRequest) -> None: ...
    def get(self, request_id: str) -> ApprovalRequest | None: ...
    def transition(
        self, request_id: str, expected_status: str, updated: ApprovalRequest
    ) -> bool: ...
    def consume(
        self, request_id: str, principal_id: str, tool_name: str,
        action_fingerprint: str | None, now: float,
    ) -> ApprovalRequest | None: ...


class InMemoryApprovalStore:
    """Thread-safe process-local store for development and tests."""

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRequest] = {}
        self._lock = RLock()

    def create(self, request: ApprovalRequest) -> None:
        with self._lock:
            if request.request_id in self._records:
                raise ValueError("approval request already exists")
            self._records[request.request_id] = request

    def get(self, request_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._records.get(request_id)

    def transition(
        self, request_id: str, expected_status: str, updated: ApprovalRequest
    ) -> bool:
        with self._lock:
            current = self._records.get(request_id)
            if current is None or current.status != expected_status:
                return False
            self._records[request_id] = updated
            return True

    def consume(
        self, request_id: str, principal_id: str, tool_name: str,
        action_fingerprint: str | None, now: float,
    ) -> ApprovalRequest | None:
        with self._lock:
            current = self._records.get(request_id)
            if (
                current is None or current.status != "approved"
                or current.principal_id != principal_id or current.tool_name != tool_name
                or current.action_fingerprint != action_fingerprint
                or current.approver_id is None or current.expires_at <= now
            ):
                return None
            updated = ApprovalRequest(
                request_id=current.request_id, principal_id=current.principal_id,
                tool_name=current.tool_name, summary=current.summary, status="consumed",
                expires_at=current.expires_at, approver_id=current.approver_id,
                reason=current.reason, action_fingerprint=current.action_fingerprint,
            )
            self._records[request_id] = updated
            return updated


class SqliteApprovalStore:
    """SQLite-backed approval store with atomic one-time consumption.

    Use a file path shared by the workers that need to coordinate. Each consume
    is one conditional SQL UPDATE, so SQLite serializes competing writers.
    """

    def __init__(self, database: str | Path, *, timeout_seconds: float = 30.0) -> None:
        self._connection = sqlite3.connect(
            str(database), timeout=timeout_seconds, isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise ValueError("timeout_seconds must be a positive finite number")
        self._connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS agentops_approvals (
                request_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at REAL NOT NULL,
                approver_id TEXT,
                reason TEXT,
                action_fingerprint TEXT
            )
        """)
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agentops_approvals_status "
            "ON agentops_approvals(status, expires_at)"
        )

    def create(self, request: ApprovalRequest) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO agentops_approvals
                (request_id, principal_id, tool_name, summary, status, expires_at,
                 approver_id, reason, action_fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._values(request),
            )

    def get(self, request_id: str) -> ApprovalRequest | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agentops_approvals WHERE request_id = ?", (request_id,)
            ).fetchone()
            return self._from_row(row) if row is not None else None

    def transition(
        self, request_id: str, expected_status: str, updated: ApprovalRequest
    ) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE agentops_approvals
                SET status = ?, approver_id = ?, reason = ?
                WHERE request_id = ? AND status = ?""",
                (updated.status, updated.approver_id, updated.reason,
                 request_id, expected_status),
            )
            return cursor.rowcount == 1

    def consume(
        self, request_id: str, principal_id: str, tool_name: str,
        action_fingerprint: str | None, now: float,
    ) -> ApprovalRequest | None:
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE agentops_approvals SET status = 'consumed'
                WHERE request_id = ? AND principal_id = ? AND tool_name = ?
                  AND status = 'approved' AND approver_id IS NOT NULL
                  AND expires_at > ? AND action_fingerprint IS ?""",
                (request_id, principal_id, tool_name, now, action_fingerprint),
            )
            if cursor.rowcount != 1:
                return None
            row = self._connection.execute(
                "SELECT * FROM agentops_approvals WHERE request_id = ?", (request_id,)
            ).fetchone()
            return self._from_row(row) if row is not None else None

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _values(request: ApprovalRequest) -> tuple[Any, ...]:
        return (
            request.request_id, request.principal_id, request.tool_name, request.summary,
            request.status, request.expires_at, request.approver_id, request.reason,
            request.action_fingerprint,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            request_id=row["request_id"], principal_id=row["principal_id"],
            tool_name=row["tool_name"], summary=row["summary"], status=row["status"],
            expires_at=row["expires_at"], approver_id=row["approver_id"],
            reason=row["reason"], action_fingerprint=row["action_fingerprint"],
        )


class ApprovalManager:
    """Approval state machine backed by an injectable store.

    The default store is process-local. Use SqliteApprovalStore for durable,
    multi-process coordination on a shared SQLite database. Host applications
    remain responsible for authenticating and authorizing approvers.
    """

    def __init__(
        self, *, clock: Callable[[], float] = time, store: ApprovalStore | None = None
    ) -> None:
        self._clock = clock
        self.store: ApprovalStore = store if store is not None else InMemoryApprovalStore()

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
            self._validate_identity(value, name)
        if (
            isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float))
            or not math.isfinite(ttl_seconds) or ttl_seconds <= 0
        ):
            raise ValueError("ttl_seconds must be a positive finite number")
        fingerprint = action_fingerprint(action) if action is not None else None
        request = ApprovalRequest(
            request_id=str(uuid4()), principal_id=principal_id, tool_name=tool_name,
            summary=summary, status="pending", expires_at=self._clock() + ttl_seconds,
            action_fingerprint=fingerprint,
        )
        self.store.create(request)
        return request

    def get(self, request_id: str) -> ApprovalRequest:
        return self._expire_if_needed(self._get_record(request_id))

    def approve(self, request_id: str, *, approver_id: str) -> ApprovalRequest:
        self._validate_identity(approver_id, "approver_id")
        request = self.get(request_id)
        if request.status != "pending":
            raise ApprovalDeniedError(
                f"Approval request {request_id!r} is {request.status}"
            )
        updated = self._replace(request, status="approved", approver_id=approver_id)
        if not self.store.transition(request_id, "pending", updated):
            latest = self.get(request_id)
            raise ApprovalDeniedError(
                f"Approval request {request_id!r} is {latest.status}"
            )
        return updated

    def deny(
        self, request_id: str, *, approver_id: str, reason: str
    ) -> ApprovalRequest:
        self._validate_identity(approver_id, "approver_id")
        self._validate_identity(reason, "reason")
        request = self.get(request_id)
        if request.status != "pending":
            raise ApprovalDeniedError(
                f"Approval request {request_id!r} is {request.status}"
            )
        updated = self._replace(
            request, status="denied", approver_id=approver_id, reason=reason
        )
        if not self.store.transition(request_id, "pending", updated):
            latest = self.get(request_id)
            raise ApprovalDeniedError(
                f"Approval request {request_id!r} is {latest.status}"
            )
        return updated

    def consume(
        self,
        request_id: str,
        principal_id: str,
        tool_name: str,
        *,
        action: Mapping[str, Any] | None = None,
    ) -> ApprovalGrant:
        request = self.get(request_id)
        if request.principal_id != principal_id or request.tool_name != tool_name:
            raise ApprovalRequiredError("Approval does not match this principal and tool")
        if request.status == "denied":
            raise ApprovalDeniedError(f"Approval request {request_id!r} was denied")
        if request.status != "approved" or request.approver_id is None:
            raise ApprovalRequiredError(
                f"Approval request {request_id!r} is {request.status}"
            )
        fingerprint = action_fingerprint(action) if action is not None else None
        if fingerprint != request.action_fingerprint:
            raise ApprovalRequiredError("Approval does not match the canonical action")
        consumed = self.store.consume(
            request_id, principal_id, tool_name, fingerprint, self._clock()
        )
        if consumed is None:
            latest = self.get(request_id)
            if latest.status == "denied":
                raise ApprovalDeniedError(f"Approval request {request_id!r} was denied")
            raise ApprovalRequiredError(
                f"Approval request {request_id!r} is {latest.status}"
            )
        return ApprovalGrant(
            request_id=consumed.request_id, principal_id=consumed.principal_id,
            tool_name=consumed.tool_name, approver_id=consumed.approver_id or "",
            action_fingerprint=consumed.action_fingerprint,
        )

    def _get_record(self, request_id: str) -> ApprovalRequest:
        record = self.store.get(request_id)
        if record is None:
            raise ApprovalRequiredError(f"Unknown approval request {request_id!r}")
        return record

    def _expire_if_needed(self, request: ApprovalRequest) -> ApprovalRequest:
        if request.status in ("pending", "approved") and self._clock() >= request.expires_at:
            expired = self._replace(request, status="expired")
            if self.store.transition(request.request_id, request.status, expired):
                return expired
            return self._get_record(request.request_id)
        return request

    @staticmethod
    def _replace(request: ApprovalRequest, **changes: object) -> ApprovalRequest:
        values = {
            "request_id": request.request_id, "principal_id": request.principal_id,
            "tool_name": request.tool_name, "summary": request.summary,
            "status": request.status, "expires_at": request.expires_at,
            "approver_id": request.approver_id, "reason": request.reason,
            "action_fingerprint": request.action_fingerprint,
        }
        values.update(changes)
        return ApprovalRequest(**values)

    @staticmethod
    def _validate_identity(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
