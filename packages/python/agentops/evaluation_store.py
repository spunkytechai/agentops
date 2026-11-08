"""Durable storage for evaluation reports and per-suite baselines."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sqlite3
from pathlib import Path
from threading import RLock
from time import time
from typing import Callable, Protocol
from uuid import uuid4

from .evaluation import EvaluationReport, EvaluationCaseResult


class EvaluationRunStoreError(ValueError):
    """Raised when a run or baseline violates store invariants."""


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    run_id: str
    suite_name: str
    created_at_ms: int
    report: EvaluationReport


class EvaluationRunStore(Protocol):
    def save(self, report: EvaluationReport, run_id: str | None = None) -> EvaluationRun: ...
    def get(self, run_id: str) -> EvaluationRun | None: ...
    def set_baseline(self, suite_name: str, run_id: str) -> None: ...
    def get_baseline(self, suite_name: str) -> EvaluationRun | None: ...


def _identity(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationRunStoreError(f"{label} must be a non-empty string")


def _payload(report: EvaluationReport) -> dict[str, object]:
    return {
        "suite_name": report.suite_name,
        "total_cases": report.total_cases,
        "passed_cases": report.passed_cases,
        "failed_cases": report.failed_cases,
        "weighted_score": report.weighted_score,
        "pass_rate": report.pass_rate,
        "case_results": [{
            "case_id": item.case_id, "score": item.score,
            "passed": item.passed, "error_type": item.error_type,
        } for item in report.case_results],
    }


def _encode(report: EvaluationReport) -> str:
    try:
        return json.dumps(_payload(report), separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EvaluationRunStoreError("report must contain finite JSON-compatible values") from exc


def _decode(value: str) -> EvaluationReport:
    try:
        data = json.loads(value)
        results = tuple(EvaluationCaseResult(
            case_id=item["case_id"], score=float(item["score"]),
            passed=item["passed"], error_type=item.get("error_type"),
        ) for item in data["case_results"])
        report = EvaluationReport(
            suite_name=data["suite_name"], total_cases=data["total_cases"],
            passed_cases=data["passed_cases"], failed_cases=data["failed_cases"],
            weighted_score=float(data["weighted_score"]), pass_rate=float(data["pass_rate"]),
            case_results=results,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EvaluationRunStoreError("stored evaluation report is invalid") from exc
    if report.total_cases != len(results) or report.passed_cases + report.failed_cases != report.total_cases:
        raise EvaluationRunStoreError("stored evaluation report counts are inconsistent")
    return report


class InMemoryEvaluationRunStore:
    """Thread-safe process-local evaluation history and baseline pointers."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or (lambda: time() * 1000)
        self._runs: dict[str, EvaluationRun] = {}
        self._baselines: dict[str, str] = {}
        self._lock = RLock()

    def save(self, report: EvaluationReport, run_id: str | None = None) -> EvaluationRun:
        identifier = run_id or str(uuid4())
        _identity(identifier, "run_id")
        _identity(report.suite_name, "suite_name")
        payload = _encode(report)
        timestamp = self._timestamp()
        record = EvaluationRun(identifier, report.suite_name, timestamp, _decode(payload))
        with self._lock:
            if identifier in self._runs:
                raise EvaluationRunStoreError("evaluation run already exists")
            self._runs[identifier] = record
        return record

    def get(self, run_id: str) -> EvaluationRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def set_baseline(self, suite_name: str, run_id: str) -> None:
        _identity(suite_name, "suite_name")
        _identity(run_id, "run_id")
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.suite_name != suite_name:
                raise EvaluationRunStoreError("baseline run must exist and belong to the requested suite")
            self._baselines[suite_name] = run_id

    def get_baseline(self, suite_name: str) -> EvaluationRun | None:
        with self._lock:
            run_id = self._baselines.get(suite_name)
            return self._runs.get(run_id) if run_id is not None else None

    def _timestamp(self) -> int:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise EvaluationRunStoreError("clock must return a non-negative finite millisecond timestamp")
        return int(value)


class SqliteEvaluationRunStore:
    """SQLite history store; baseline changes are suite-checked and atomic."""

    def __init__(
        self, database: str | Path, *, clock: Callable[[], float] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        self._clock = clock or (lambda: time() * 1000)
        self._connection = sqlite3.connect(
            str(database), timeout=timeout_seconds, isolation_level=None, check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS agentops_evaluation_runs (
                run_id TEXT PRIMARY KEY, suite_name TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL, report_json TEXT NOT NULL
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS agentops_evaluation_baselines (
                suite_name TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES agentops_evaluation_runs(run_id)
            )
        """)

    def save(self, report: EvaluationReport, run_id: str | None = None) -> EvaluationRun:
        identifier = run_id or str(uuid4())
        _identity(identifier, "run_id")
        _identity(report.suite_name, "suite_name")
        payload = _encode(report)
        timestamp = self._timestamp()
        with self._lock:
            self._connection.execute(
                "INSERT INTO agentops_evaluation_runs (run_id, suite_name, created_at_ms, report_json) VALUES (?, ?, ?, ?)",
                (identifier, report.suite_name, timestamp, payload),
            )
        return EvaluationRun(identifier, report.suite_name, timestamp, _decode(payload))

    def get(self, run_id: str) -> EvaluationRun | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agentops_evaluation_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            return self._from_row(row) if row is not None else None

    def set_baseline(self, suite_name: str, run_id: str) -> None:
        _identity(suite_name, "suite_name")
        _identity(run_id, "run_id")
        with self._lock:
            cursor = self._connection.execute("""
                INSERT INTO agentops_evaluation_baselines (suite_name, run_id)
                SELECT ?, run_id FROM agentops_evaluation_runs
                WHERE run_id = ? AND suite_name = ?
                ON CONFLICT(suite_name) DO UPDATE SET run_id = excluded.run_id
            """, (suite_name, run_id, suite_name))
            if cursor.rowcount != 1:
                raise EvaluationRunStoreError("baseline run must exist and belong to the requested suite")

    def get_baseline(self, suite_name: str) -> EvaluationRun | None:
        with self._lock:
            row = self._connection.execute("""
                SELECT runs.* FROM agentops_evaluation_runs AS runs
                JOIN agentops_evaluation_baselines AS baselines ON baselines.run_id = runs.run_id
                WHERE baselines.suite_name = ?
            """, (suite_name,)).fetchone()
            return self._from_row(row) if row is not None else None

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _timestamp(self) -> int:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise EvaluationRunStoreError("clock must return a non-negative finite millisecond timestamp")
        return int(value)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> EvaluationRun:
        report = _decode(row["report_json"])
        if report.suite_name != row["suite_name"]:
            raise EvaluationRunStoreError("stored run suite does not match its report")
        return EvaluationRun(row["run_id"], row["suite_name"], row["created_at_ms"], report)
