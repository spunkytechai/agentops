/** Deterministic, provider-neutral evaluation and regression primitives. */

function freezeJson<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) freezeJson(child);
    Object.freeze(value);
  }
  return value;
}

function cloneJson(value: unknown): unknown {
  return JSON.parse(canonicalJson(value)) as unknown;
}

function canonicalJson(value: unknown): string {
  const normalize = (item: unknown): unknown => {
    if (item === null || typeof item === "string" || typeof item === "boolean") return item;
    if (typeof item === "number") {
      if (!Number.isFinite(item) || (Number.isInteger(item) && !Number.isSafeInteger(item))) throw new TypeError("evaluation values must be finite JSON-compatible data");
      return item;
    }
    if (Array.isArray(item)) return item.map(normalize);
    if (typeof item === "object") {
      if (Object.getPrototypeOf(item) !== Object.prototype && Object.getPrototypeOf(item) !== null) {
        throw new TypeError("evaluation values must be finite JSON-compatible data");
      }
      const record = item as Record<string, unknown>;
      const result: Record<string, unknown> = {};
      for (const key of Object.keys(record).sort()) {
        if (record[key] === undefined) throw new TypeError("evaluation values must be finite JSON-compatible data");
        result[key] = normalize(record[key]);
      }
      return result;
    }
    throw new TypeError("evaluation values must be finite JSON-compatible data");
  };
  try {
    return JSON.stringify(normalize(value));
  } catch {
    throw new TypeError("evaluation values must be finite JSON-compatible data");
  }
}

export interface EvaluationCaseOptions {
  readonly weight?: number;
}

export class EvaluationCase {
  readonly caseId: string;
  readonly input: unknown;
  readonly expected: unknown;
  readonly weight: number;

  constructor(caseId: string, input: unknown, expected: unknown, options: EvaluationCaseOptions = {}) {
    const weight = options.weight ?? 1;
    if (typeof caseId !== "string" || caseId.trim().length === 0) {
      throw new TypeError("caseId must be a non-empty string");
    }
    if (!Number.isFinite(weight) || weight <= 0) {
      throw new TypeError("weight must be a positive finite number");
    }
    this.caseId = caseId;
    this.input = freezeJson(JSON.parse(canonicalJson(input)) as unknown);
    this.expected = freezeJson(JSON.parse(canonicalJson(expected)) as unknown);
    this.weight = weight;
    Object.freeze(this);
  }
}

export interface EvaluationMetric {
  readonly name: string;
  score(expected: unknown, actual: unknown): number;
}

export class ExactMatchMetric implements EvaluationMetric {
  readonly name = "exact_match";
  score(expected: unknown, actual: unknown): number {
    return canonicalJson(expected) === canonicalJson(actual) ? 1 : 0;
  }
}

export class NumericToleranceMetric implements EvaluationMetric {
  readonly name = "numeric_tolerance";
  readonly absoluteTolerance: number;

  constructor(absoluteTolerance: number) {
    if (!Number.isFinite(absoluteTolerance) || absoluteTolerance < 0) {
      throw new TypeError("absoluteTolerance must be a non-negative finite number");
    }
    this.absoluteTolerance = absoluteTolerance;
    Object.freeze(this);
  }

  score(expected: unknown, actual: unknown): number {
    if (typeof expected !== "number" || typeof actual !== "number" ||
        !Number.isFinite(expected) || !Number.isFinite(actual)) return 0;
    return Math.abs(expected - actual) <= this.absoluteTolerance ? 1 : 0;
  }
}

export interface EvaluationCaseResult {
  readonly caseId: string;
  readonly score: number;
  readonly passed: boolean;
  readonly errorType?: string;
}

export interface EvaluationReport {
  readonly suiteName: string;
  readonly totalCases: number;
  readonly passedCases: number;
  readonly failedCases: number;
  readonly weightedScore: number;
  readonly passRate: number;
  readonly caseResults: readonly EvaluationCaseResult[];
}

export interface EvaluationSuiteOptions {
  readonly metric?: EvaluationMetric;
  readonly passThreshold?: number;
}

export class EvaluationSuite {
  readonly name: string;
  readonly cases: readonly EvaluationCase[];
  readonly metric: EvaluationMetric;
  readonly passThreshold: number;

  constructor(name: string, cases: readonly EvaluationCase[], options: EvaluationSuiteOptions = {}) {
    const passThreshold = options.passThreshold ?? 1;
    if (typeof name !== "string" || name.trim().length === 0) {
      throw new TypeError("suite name must be a non-empty string");
    }
    if (!Number.isFinite(passThreshold) || passThreshold < 0 || passThreshold > 1) {
      throw new TypeError("passThreshold must be between 0 and 1");
    }
    if (cases.length === 0) throw new TypeError("an evaluation suite must contain at least one case");
    if (cases.some((item) => !(item instanceof EvaluationCase))) {
      throw new TypeError("cases must contain EvaluationCase instances");
    }
    const ids = cases.map((item) => item.caseId);
    if (new Set(ids).size !== ids.length) throw new TypeError("caseId values must be unique within a suite");
    this.name = name;
    this.cases = Object.freeze([...cases]);
    this.metric = options.metric ?? new ExactMatchMetric();
    this.passThreshold = passThreshold;
    Object.freeze(this);
  }

  async run(operation: (input: unknown) => unknown | Promise<unknown>): Promise<EvaluationReport> {
    const results: EvaluationCaseResult[] = [];
    for (const item of this.cases) {
      let actual: unknown;
      try {
        actual = await operation(cloneJson(item.input));
      } catch (error) {
        results.push({
          caseId: item.caseId,
          score: 0,
          passed: false,
          errorType: error instanceof Error ? error.name : "UnknownError",
        });
        continue;
      }
      const score = this.metric.score(cloneJson(item.expected), actual);
      if (typeof score !== "number" || !Number.isFinite(score) || score < 0 || score > 1) {
        throw new TypeError("metric score must be finite and between 0 and 1");
      }
      results.push({ caseId: item.caseId, score, passed: score >= this.passThreshold });
    }
    const totalWeight = this.cases.reduce((sum, item) => sum + item.weight, 0);
    const weightedScore = results.reduce(
      (sum, result, index) => sum + result.score * this.cases[index]!.weight, 0,
    ) / totalWeight;
    const passedCases = results.filter((item) => item.passed).length;
    return Object.freeze({
      suiteName: this.name,
      totalCases: results.length,
      passedCases,
      failedCases: results.length - passedCases,
      weightedScore,
      passRate: passedCases / results.length,
      caseResults: Object.freeze(results),
    });
  }
}

export class EvaluationRegressionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvaluationRegressionError";
  }
}

export interface EvaluationRegression {
  readonly regressed: boolean;
  readonly scoreDelta: number;
  readonly regressedCaseIds: readonly string[];
}

export function compareEvaluations(
  baseline: EvaluationReport,
  candidate: EvaluationReport,
  maxScoreDrop = 0,
): EvaluationRegression {
  if (!Number.isFinite(maxScoreDrop) || maxScoreDrop < 0 || maxScoreDrop > 1) {
    throw new TypeError("maxScoreDrop must be between 0 and 1");
  }
  if (baseline.suiteName !== candidate.suiteName) {
    throw new EvaluationRegressionError("reports must belong to the same suite");
  }
  const baselineScores = new Map(baseline.caseResults.map((item) => [item.caseId, item.score]));
  const candidateScores = new Map(candidate.caseResults.map((item) => [item.caseId, item.score]));
  if (baselineScores.size !== baseline.totalCases || candidateScores.size !== candidate.totalCases ||
      baselineScores.size !== candidateScores.size ||
      [...baselineScores.keys()].some((id) => !candidateScores.has(id))) {
    throw new EvaluationRegressionError("reports must contain the same unique case IDs");
  }
  const regressedCaseIds = [...baselineScores].filter(
    ([id, score]) => candidateScores.get(id)! < score - maxScoreDrop,
  ).map(([id]) => id);
  const scoreDelta = candidate.weightedScore - baseline.weightedScore;
  return Object.freeze({
    regressed: scoreDelta < -maxScoreDrop || regressedCaseIds.length > 0,
    scoreDelta,
    regressedCaseIds: Object.freeze(regressedCaseIds),
  });
}
