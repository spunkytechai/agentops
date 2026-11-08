import unittest
import json
from pathlib import Path

from agentops import (
    EvaluationCase,
    EvaluationRegressionError,
    EvaluationSuite,
    NumericToleranceMetric,
    EvaluationMetric,
    ExactMatchMetric,
    compare_evaluations,
)


class EvaluationEngineTests(unittest.TestCase):
    def test_suite_scores_weighted_cases_and_reports_pass_rate(self):
        suite = EvaluationSuite(
            "conformance",
            (
                EvaluationCase("same", "alpha", "alpha", weight=1),
                EvaluationCase("same-json", {"b": 2, "a": 1}, {"a": 1, "b": 2}, weight=2),
                EvaluationCase("different", "wrong", "right", weight=1),
            ),
            metric=ExactMatchMetric(),
        )
        report = suite.run(lambda value: value)
        self.assertEqual(report.total_cases, 3)
        self.assertEqual(report.passed_cases, 2)
        self.assertEqual(report.failed_cases, 1)
        self.assertAlmostEqual(report.weighted_score, 0.75)
        self.assertAlmostEqual(report.pass_rate, 2 / 3)
        self.assertEqual([item.case_id for item in report.case_results], [
            "same", "same-json", "different"
        ])

    def test_numeric_tolerance_metric_scores_within_and_outside_boundary(self):
        from agentops import NumericToleranceMetric
        metric = NumericToleranceMetric(0.5)
        self.assertEqual(metric.score(10, 10.5), 1.0)
        self.assertEqual(metric.score(10, 10.5001), 0.0)
        self.assertEqual(metric.score(True, 1), 0.0)

    def test_exact_match_uses_json_semantics_for_numbers_and_booleans(self):
        metric = ExactMatchMetric()
        self.assertEqual(metric.score(1, 1.0), 1.0)
        self.assertEqual(metric.score(True, 1), 0.0)

    async def test_async_suite_runs_awaitable_operations(self):
        import asyncio
        suite = EvaluationSuite("async", (EvaluationCase("one", 2, 4),))
        async def operation(value):
            await asyncio.sleep(0)
            return value * 2
        report = await suite.run_async(operation)
        self.assertEqual(report.weighted_score, 1.0)

    def test_async_metric_receives_a_copy_of_expected_data(self):
        import asyncio

        expected = {"nested": {"value": 7}}

        class MutatingMetric:
            name = "mutating"

            def score(self, actual_expected, actual):
                actual_expected["nested"]["value"] = 999
                return 1.0

        case = EvaluationCase("one", {"input": True}, expected)
        suite = EvaluationSuite("async-copy", (case,), metric=MutatingMetric())

        async def operation(value):
            return value

        asyncio.run(suite.run_async(operation))
        self.assertEqual(case.expected, expected)

    def test_case_exceptions_are_recorded_without_error_messages(self):
        suite = EvaluationSuite("errors", (EvaluationCase("boom", "input", "expected"),))
        report = suite.run(lambda _: (_ for _ in ()).throw(RuntimeError("contains secret")))
        self.assertEqual(report.case_results[0].score, 0.0)
        self.assertEqual(report.case_results[0].error_type, "RuntimeError")
        self.assertFalse(hasattr(report.case_results[0], "error_message"))

    def test_regression_comparison_identifies_case_and_aggregate_drop(self):
        suite = EvaluationSuite(
            "regression",
            (EvaluationCase("a", "a", "a"), EvaluationCase("b", "b", "b")),
        )
        baseline = suite.run(lambda value: value)
        candidate = suite.run(lambda value: "wrong" if value == "b" else value)
        regression = compare_evaluations(baseline, candidate)
        self.assertTrue(regression.regressed)
        self.assertAlmostEqual(regression.score_delta, -0.5)
        self.assertEqual(regression.regressed_case_ids, ("b",))

    def test_regression_comparison_rejects_different_case_sets(self):
        a = EvaluationSuite("same", (EvaluationCase("a", 1, 1),)).run(lambda x: x)
        b = EvaluationSuite("same", (EvaluationCase("b", 1, 1),)).run(lambda x: x)
        with self.assertRaises(EvaluationRegressionError):
            compare_evaluations(a, b)

    def test_shared_conformance_fixture_matches_python_results(self):
        fixture_path = Path(__file__).resolve().parents[3] / "conformance" / "fixtures" / "evaluations.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases = tuple(EvaluationCase(
            item["id"], item["input"], item["expected"], weight=item["weight"]
        ) for item in fixture["cases"])
        report = EvaluationSuite(
            fixture["suite"], cases, pass_threshold=fixture["pass_threshold"]
        ).run(lambda value: next(item["actual"] for item in fixture["cases"] if item["input"] == value))
        self.assertEqual(report.total_cases, fixture["expected"]["total_cases"])
        self.assertEqual(report.passed_cases, fixture["expected"]["passed_cases"])
        self.assertEqual(report.failed_cases, fixture["expected"]["failed_cases"])
        self.assertAlmostEqual(report.weighted_score, fixture["expected"]["weighted_score"])
        self.assertAlmostEqual(report.pass_rate, fixture["expected"]["pass_rate"])

    def test_invalid_case_weights_and_metric_scores_are_rejected(self):
        with self.assertRaises(ValueError):
            EvaluationCase("bad", 1, 1, weight=0)
        class InvalidMetric:
            name = "invalid"

            def score(self, _expected, _actual):
                return 2

        suite = EvaluationSuite("bad-metric", (EvaluationCase("a", 1, 1),), metric=InvalidMetric())
        with self.assertRaises(ValueError):
            suite.run(lambda x: x)


if __name__ == "__main__":
    unittest.main()
