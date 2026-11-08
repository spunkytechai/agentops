import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  EvaluationCase,
  EvaluationRegressionError,
  EvaluationSuite,
  NumericToleranceMetric,
  ExactMatchMetric,
  compareEvaluations,
} from "../dist/index.js";

test("suite scores weighted cases and reports pass rate", async () => {
  const suite = new EvaluationSuite("conformance", [
    new EvaluationCase("same", "alpha", "alpha", { weight: 1 }),
    new EvaluationCase("same-json", { b: 2, a: 1 }, { a: 1, b: 2 }, { weight: 2 }),
    new EvaluationCase("different", "wrong", "right", { weight: 1 }),
  ], { metric: new ExactMatchMetric() });
  const report = await suite.run(async (value) => value);
  assert.equal(report.totalCases, 3);
  assert.equal(report.passedCases, 2);
  assert.equal(report.failedCases, 1);
  assert.equal(report.weightedScore, 0.75);
  assert.equal(report.passRate, 2 / 3);
  assert.deepEqual(report.caseResults.map((item) => item.caseId), ["same", "same-json", "different"]);
});

test("numeric tolerance metric scores within and outside boundary", () => {
  const metric = new NumericToleranceMetric(0.5);
  assert.equal(metric.score(10, 10.5), 1);
  assert.equal(metric.score(10, 10.5001), 0);
  assert.equal(metric.score(true, 1), 0);
});

test("exact match uses JSON semantics for numbers and booleans", () => {
  const metric = new ExactMatchMetric();
  assert.equal(metric.score(1, 1.0), 1);
  assert.equal(metric.score(true, 1), 0);
});

test("suite gives each operation a fresh immutable JSON input snapshot", async () => {
  const input = { nested: { value: 1 } };
  const suite = new EvaluationSuite("immutable-input", [
    new EvaluationCase("one", input, 1),
    new EvaluationCase("two", input, 1),
  ]);
  const seen = [];
  const report = await suite.run(async (value) => {
    let mutationBlocked = false;
    try { value.nested.value = 2; } catch (error) { mutationBlocked = error instanceof TypeError; }
    assert.equal(mutationBlocked, true);
    seen.push(value.nested.value);
    return 1;
  });
  assert.deepEqual(seen, [1, 1]);
  assert.equal(report.weightedScore, 1);
});

test("case exceptions are recorded without exposing error messages", async () => {
  const suite = new EvaluationSuite("errors", [new EvaluationCase("boom", "input", "expected")]);
  const report = await suite.run(async () => { throw new Error("contains secret"); });
  assert.equal(report.caseResults[0].score, 0);
  assert.equal(report.caseResults[0].errorType, "Error");
  assert.equal("errorMessage" in report.caseResults[0], false);
});

test("regression comparison identifies case and aggregate score drop", async () => {
  const suite = new EvaluationSuite("regression", [
    new EvaluationCase("a", "a", "a"),
    new EvaluationCase("b", "b", "b"),
  ]);
  const baseline = await suite.run(async (value) => value);
  const candidate = await suite.run(async (value) => value === "b" ? "wrong" : value);
  const regression = compareEvaluations(baseline, candidate);
  assert.equal(regression.regressed, true);
  assert.equal(regression.scoreDelta, -0.5);
  assert.deepEqual(regression.regressedCaseIds, ["b"]);
});

test("regression comparison rejects reports with different case sets", async () => {
  const a = await new EvaluationSuite("same", [new EvaluationCase("a", 1, 1)]).run(async (x) => x);
  const b = await new EvaluationSuite("same", [new EvaluationCase("b", 1, 1)]).run(async (x) => x);
  assert.throws(() => compareEvaluations(a, b), EvaluationRegressionError);
});

test("shared conformance fixture matches TypeScript results", async () => {
  const fixture = JSON.parse(readFileSync("../../conformance/fixtures/evaluations.json", "utf8"));
  const cases = fixture.cases.map((item) => new EvaluationCase(
    item.id, item.input, item.expected, { weight: item.weight },
  ));
  const report = await new EvaluationSuite(fixture.suite, cases, {
    passThreshold: fixture.pass_threshold,
  }).run(async (input) => fixture.cases.find((item) => JSON.stringify(item.input) === JSON.stringify(input)).actual);
  assert.equal(report.totalCases, fixture.expected.total_cases);
  assert.equal(report.passedCases, fixture.expected.passed_cases);
  assert.equal(report.failedCases, fixture.expected.failed_cases);
  assert.equal(report.weightedScore, fixture.expected.weighted_score);
  assert.equal(report.passRate, fixture.expected.pass_rate);
});

test("invalid case weights and metric scores are rejected", async () => {
  assert.throws(() => new EvaluationCase("bad", 1, 1, { weight: 0 }), TypeError);
  const suite = new EvaluationSuite("bad-metric", [new EvaluationCase("a", 1, 1)], {
    metric: { name: "invalid", score: () => 2 },
  });
  await assert.rejects(suite.run(async (x) => x), /score must be finite and between 0 and 1/);
});
