"""Deterministic, provider-neutral evaluation and regression primitives."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from collections.abc import Callable, Iterable
from typing import Any, Protocol


def _validate_json(value: Any) -> None:
    if value is None or type(value) in (str, bool):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("evaluation integers must be JavaScript-safe")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("evaluation values must be finite JSON-compatible data")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json(item)
        return
    raise ValueError("evaluation values must be finite JSON-compatible data")


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right, strict=True))
    return type(left) is type(right) and left == right


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    input: Any
    expected: Any
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)) or not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("weight must be a positive finite number")
        _validate_json(self.input)
        _validate_json(self.expected)


class EvaluationMetric(Protocol):
    """A deterministic scorer returning a value in the inclusive range [0, 1]."""
    name: str

    def score(self, expected: Any, actual: Any) -> float: ...


@dataclass(frozen=True, slots=True)
class ExactMatchMetric:
    name: str = "exact_match"

    def score(self, expected: Any, actual: Any) -> float:
        _validate_json(expected)
        _validate_json(actual)
        return 1.0 if _json_equal(expected, actual) else 0.0


@dataclass(frozen=True, slots=True)
class NumericToleranceMetric:
    absolute_tolerance: float
    name: str = "numeric_tolerance"

    def __post_init__(self) -> None:
        if isinstance(self.absolute_tolerance, bool) or not isinstance(self.absolute_tolerance, (int, float)) or not math.isfinite(self.absolute_tolerance) or self.absolute_tolerance < 0:
            raise ValueError("absolute_tolerance must be a non-negative finite number")

    def score(self, expected: Any, actual: Any) -> float:
        if isinstance(expected, bool) or isinstance(actual, bool):
            return 0.0
        if not isinstance(expected, (int, float)) or not isinstance(actual, (int, float)):
            return 0.0
        if not math.isfinite(expected) or not math.isfinite(actual):
            return 0.0
        return 1.0 if abs(expected - actual) <= self.absolute_tolerance else 0.0


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    case_id: str
    score: float
    passed: bool
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    suite_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    weighted_score: float
    pass_rate: float
    case_results: tuple[EvaluationCaseResult, ...]


class EvaluationSuite:
    """Runs a fixed dataset against an operation and aggregates deterministic scores."""

    def __init__(
        self,
        name: str,
        cases: Iterable[EvaluationCase],
        *,
        metric: EvaluationMetric | None = None,
        pass_threshold: float = 1.0,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("suite name must be a non-empty string")
        if isinstance(pass_threshold, bool) or not isinstance(pass_threshold, (int, float)) or not math.isfinite(pass_threshold) or not 0 <= pass_threshold <= 1:
            raise ValueError("pass_threshold must be between 0 and 1")
        snapshot = tuple(cases)
        if not snapshot:
            raise ValueError("an evaluation suite must contain at least one case")
        if any(not isinstance(case, EvaluationCase) for case in snapshot):
            raise TypeError("cases must contain EvaluationCase instances")
        ids = [case.case_id for case in snapshot]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique within a suite")
        self.name = name
        self.cases = snapshot
        self.metric = metric or ExactMatchMetric()
        self.pass_threshold = float(pass_threshold)

    def run(self, operation: Callable[[Any], Any]) -> EvaluationReport:
        results: list[EvaluationCaseResult] = []
        for case in self.cases:
            try:
                actual = operation(deepcopy(case.input))
            except Exception as exc:
                results.append(EvaluationCaseResult(case.case_id, 0.0, False, type(exc).__name__))
                continue
            score = self.metric.score(deepcopy(case.expected), actual)
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("metric score must be finite and between 0 and 1")
            value = float(score)
            results.append(EvaluationCaseResult(case.case_id, value, value >= self.pass_threshold))
        total_weight = sum(case.weight for case in self.cases)
        weighted_score = sum(
            result.score * case.weight for result, case in zip(results, self.cases, strict=True)
        ) / total_weight
        passed = sum(result.passed for result in results)
        return EvaluationReport(
            self.name, len(results), passed, len(results) - passed,
            weighted_score, passed / len(results), tuple(results),
        )

    async def run_async(self, operation: Callable[[Any], Any]) -> EvaluationReport:
        """Run async or sync operations sequentially; no parallelism is implied."""
        results: list[EvaluationCaseResult] = []
        for case in self.cases:
            try:
                actual = operation(deepcopy(case.input))
                if hasattr(actual, "__await__"):
                    actual = await actual
            except Exception as exc:
                results.append(EvaluationCaseResult(case.case_id, 0.0, False, type(exc).__name__))
                continue
            score = self.metric.score(case.expected, actual)
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("metric score must be finite and between 0 and 1")
            value = float(score)
            results.append(EvaluationCaseResult(case.case_id, value, value >= self.pass_threshold))
        total_weight = sum(case.weight for case in self.cases)
        weighted_score = sum(
            result.score * case.weight for result, case in zip(results, self.cases, strict=True)
        ) / total_weight
        passed = sum(result.passed for result in results)
        return EvaluationReport(
            self.name, len(results), passed, len(results) - passed,
            weighted_score, passed / len(results), tuple(results),
        )


class EvaluationRegressionError(ValueError):
    """Raised when baseline and candidate reports cannot be compared safely."""


@dataclass(frozen=True, slots=True)
class EvaluationRegression:
    regressed: bool
    score_delta: float
    regressed_case_ids: tuple[str, ...]


def compare_evaluations(
    baseline: EvaluationReport,
    candidate: EvaluationReport,
    *,
    max_score_drop: float = 0.0,
) -> EvaluationRegression:
    if isinstance(max_score_drop, bool) or not isinstance(max_score_drop, (int, float)) or not math.isfinite(max_score_drop) or not 0 <= max_score_drop <= 1:
        raise ValueError("max_score_drop must be between 0 and 1")
    if baseline.suite_name != candidate.suite_name:
        raise EvaluationRegressionError("reports must belong to the same suite")
    baseline_results = {item.case_id: item.score for item in baseline.case_results}
    candidate_results = {item.case_id: item.score for item in candidate.case_results}
    if baseline_results.keys() != candidate_results.keys() or len(baseline_results) != baseline.total_cases or len(candidate_results) != candidate.total_cases:
        raise EvaluationRegressionError("reports must contain the same unique case IDs")
    regressed_ids = tuple(
        case_id for case_id, score in baseline_results.items()
        if candidate_results[case_id] < score - max_score_drop
    )
    delta = candidate.weighted_score - baseline.weighted_score
    return EvaluationRegression(
        delta < -max_score_drop or bool(regressed_ids), delta, regressed_ids
    )
