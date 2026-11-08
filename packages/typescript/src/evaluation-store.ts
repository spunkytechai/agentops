/** Persistent evaluation history and per-suite baseline pointers. */
import type { EvaluationReport } from "./evaluation.js";
import type { SqliteDatabase } from "./approvals.js";

export interface EvaluationRun {
  readonly runId: string;
  readonly suiteName: string;
  readonly createdAtMs: number;
  readonly report: EvaluationReport;
}
export interface EvaluationRunStore {
  save(report: EvaluationReport, runId?: string): EvaluationRun;
  get(runId: string): EvaluationRun | undefined;
  setBaseline(suiteName: string, runId: string): void;
  getBaseline(suiteName: string): EvaluationRun | undefined;
}
export class EvaluationRunStoreError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvaluationRunStoreError";
  }
}

function identity(value: string, label: string): void {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new EvaluationRunStoreError(label + " must be a non-empty string");
  }
}
function encode(report: EvaluationReport): string {
  try {
    const value = JSON.stringify({
      suite_name: report.suiteName,
      total_cases: report.totalCases,
      passed_cases: report.passedCases,
      failed_cases: report.failedCases,
      weighted_score: report.weightedScore,
      pass_rate: report.passRate,
      case_results: report.caseResults.map((item) => ({
        case_id: item.caseId, score: item.score, passed: item.passed,
        error_type: item.errorType ?? null,
      })),
    });
    if (value === undefined) throw new TypeError();
    return value;
  } catch {
    throw new EvaluationRunStoreError("report must contain finite JSON-compatible values");
  }
}
function decode(value: string): EvaluationReport {
  let raw: unknown;
  try { raw = JSON.parse(value) as unknown; } catch {
    throw new EvaluationRunStoreError("stored evaluation report is invalid");
  }
  if (typeof raw !== "object" || raw === null) throw new EvaluationRunStoreError("stored evaluation report is invalid");
  const row = raw as Record<string, unknown>;
  if (typeof row.suite_name !== "string" || row.suite_name.trim().length === 0 || !Number.isInteger(row.total_cases) ||
      !Number.isInteger(row.passed_cases) || !Number.isInteger(row.failed_cases) ||
      typeof row.weighted_score !== "number" || !Number.isFinite(row.weighted_score) ||
      typeof row.pass_rate !== "number" || !Number.isFinite(row.pass_rate) ||
      !Array.isArray(row.case_results)) {
    throw new EvaluationRunStoreError("stored evaluation report is invalid");
  }
  const results = row.case_results.map((rawItem) => {
    if (typeof rawItem !== "object" || rawItem === null) {
      throw new EvaluationRunStoreError("stored evaluation case result is invalid");
    }
    const item = rawItem as Record<string, unknown>;
    if (typeof item.case_id !== "string" || typeof item.score !== "number" ||
        !Number.isFinite(item.score) || item.score < 0 || item.score > 1 || typeof item.passed !== "boolean" ||
        (item.error_type !== null && item.error_type !== undefined && typeof item.error_type !== "string")) {
      throw new EvaluationRunStoreError("stored evaluation case result is invalid");
    }
    return Object.freeze({
      caseId: item.case_id, score: item.score, passed: item.passed,
      ...(typeof item.error_type === "string" ? { errorType: item.error_type } : {}),
    });
  });
  if (row.total_cases !== results.length || (row.total_cases as number) <= 0 ||
      (row.passed_cases as number) + (row.failed_cases as number) !== row.total_cases ||
      (row.passed_cases as number) !== results.filter((item) => item.passed).length ||
      (row.failed_cases as number) !== results.length - (row.passed_cases as number) ||
      row.weighted_score < 0 || row.weighted_score > 1 || row.pass_rate < 0 || row.pass_rate > 1 ||
      Math.abs(row.pass_rate - (row.passed_cases as number) / (row.total_cases as number)) > 1e-12) {
    throw new EvaluationRunStoreError("stored evaluation report counts are inconsistent");
  }
  return Object.freeze({
    suiteName: row.suite_name,
    totalCases: row.total_cases as number,
    passedCases: row.passed_cases as number,
    failedCases: row.failed_cases as number,
    weightedScore: row.weighted_score,
    passRate: row.pass_rate,
    caseResults: Object.freeze(results),
  });
}
function run(runId: string, suiteName: string, createdAtMs: number, report: EvaluationReport): EvaluationRun {
  return Object.freeze({ runId, suiteName, createdAtMs, report });
}

export class InMemoryEvaluationRunStore implements EvaluationRunStore {
  private readonly runs = new Map<string, EvaluationRun>();
  private readonly baselines = new Map<string, string>();
  constructor(private readonly clock: () => number = Date.now) {}

  save(report: EvaluationReport, runId = globalThis.crypto.randomUUID()): EvaluationRun {
    identity(runId, "runId");
    identity(report.suiteName, "suiteName");
    if (this.runs.has(runId)) throw new EvaluationRunStoreError("evaluation run already exists");
    const createdAtMs = this.timestamp();
    const saved = run(runId, report.suiteName, createdAtMs, decode(encode(report)));
    this.runs.set(runId, saved);
    return saved;
  }
  get(runId: string): EvaluationRun | undefined { return this.runs.get(runId); }
  setBaseline(suiteName: string, runId: string): void {
    identity(suiteName, "suiteName");
    identity(runId, "runId");
    const saved = this.runs.get(runId);
    if (saved === undefined || saved.suiteName !== suiteName) {
      throw new EvaluationRunStoreError("baseline run must exist and belong to the requested suite");
    }
    this.baselines.set(suiteName, runId);
  }
  getBaseline(suiteName: string): EvaluationRun | undefined {
    const runId = this.baselines.get(suiteName);
    return runId === undefined ? undefined : this.runs.get(runId);
  }
  private timestamp(): number {
    const value = this.clock();
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new EvaluationRunStoreError("clock must return a non-negative safe millisecond timestamp");
    }
    return value;
  }
}

export class SqliteEvaluationRunStore implements EvaluationRunStore {
  constructor(private readonly database: SqliteDatabase, private readonly clock: () => number = Date.now) {
    database.exec("PRAGMA foreign_keys = ON");
    database.exec("CREATE TABLE IF NOT EXISTS agentops_evaluation_runs (run_id TEXT PRIMARY KEY, suite_name TEXT NOT NULL, created_at_ms INTEGER NOT NULL, report_json TEXT NOT NULL)");
    database.exec("CREATE TABLE IF NOT EXISTS agentops_evaluation_baselines (suite_name TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agentops_evaluation_runs(run_id))");
  }
  save(report: EvaluationReport, runId = globalThis.crypto.randomUUID()): EvaluationRun {
    identity(runId, "runId");
    identity(report.suiteName, "suiteName");
    const createdAtMs = this.timestamp();
    const payload = encode(report);
    const validatedReport = decode(payload);
    try {
      this.database.prepare("INSERT INTO agentops_evaluation_runs (run_id, suite_name, created_at_ms, report_json) VALUES (?, ?, ?, ?)").run(
        runId, validatedReport.suiteName, createdAtMs, payload,
      );
    } catch (error) {
      if (error instanceof Error && /UNIQUE|PRIMARY KEY|constraint/i.test(error.message)) {
        throw new EvaluationRunStoreError("evaluation run already exists");
      }
      throw error;
    }
    return run(runId, validatedReport.suiteName, createdAtMs, validatedReport);
  }
  get(runId: string): EvaluationRun | undefined {
    const row = this.database.prepare("SELECT * FROM agentops_evaluation_runs WHERE run_id = ?").get(runId);
    return row === undefined ? undefined : this.fromRow(row);
  }
  setBaseline(suiteName: string, runId: string): void {
    identity(suiteName, "suiteName");
    identity(runId, "runId");
    const result = this.database.prepare(
      "INSERT INTO agentops_evaluation_baselines (suite_name, run_id) " +
      "SELECT ?, run_id FROM agentops_evaluation_runs WHERE run_id = ? AND suite_name = ? " +
      "ON CONFLICT(suite_name) DO UPDATE SET run_id = excluded.run_id",
    ).run(suiteName, runId, suiteName);
    if (result.changes !== 1) {
      throw new EvaluationRunStoreError("baseline run must exist and belong to the requested suite");
    }
  }
  getBaseline(suiteName: string): EvaluationRun | undefined {
    const row = this.database.prepare(
      "SELECT runs.* FROM agentops_evaluation_runs AS runs " +
      "JOIN agentops_evaluation_baselines AS baselines ON baselines.run_id = runs.run_id " +
      "WHERE baselines.suite_name = ?",
    ).get(suiteName);
    return row === undefined ? undefined : this.fromRow(row);
  }
  private timestamp(): number {
    const value = this.clock();
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new EvaluationRunStoreError("clock must return a non-negative safe millisecond timestamp");
    }
    return value;
  }
  private fromRow(value: unknown): EvaluationRun {
    if (typeof value !== "object" || value === null) {
      throw new EvaluationRunStoreError("SQLite returned an invalid evaluation run");
    }
    const row = value as Record<string, unknown>;
    if (typeof row.run_id !== "string" || typeof row.suite_name !== "string" ||
        typeof row.created_at_ms !== "number" || !Number.isSafeInteger(row.created_at_ms) ||
        typeof row.report_json !== "string") {
      throw new EvaluationRunStoreError("SQLite returned an invalid evaluation run");
    }
    const report = decode(row.report_json);
    if (report.suiteName !== row.suite_name) {
      throw new EvaluationRunStoreError("stored run suite does not match its report");
    }
    return run(row.run_id, row.suite_name, row.created_at_ms, report);
  }
}
