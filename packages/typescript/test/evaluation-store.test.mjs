import test from "node:test";
import assert from "node:assert/strict";
import Database from "better-sqlite3";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  EvaluationCase,
  EvaluationRunStoreError,
  EvaluationSuite,
  InMemoryEvaluationRunStore,
  SqliteEvaluationRunStore,
} from "../dist/index.js";

const makeReport = async (suiteName = "support-quality") => new EvaluationSuite(
  suiteName,
  [new EvaluationCase("greeting", "hello", "hello")],
).run(async (value) => value);

test("in-memory store saves runs and moves baseline", async () => {
  const report = await makeReport();
  const store = new InMemoryEvaluationRunStore(() => 1_800_000_000_000);
  const first = store.save(report, "run-1");
  assert.equal(first.runId, "run-1");
  assert.equal(first.createdAtMs, 1_800_000_000_000);
  assert.deepEqual(store.get("run-1"), first);
  store.setBaseline("support-quality", "run-1");
  assert.deepEqual(store.getBaseline("support-quality"), first);

  const candidate = store.save(report, "run-2");
  store.setBaseline("support-quality", "run-2");
  assert.deepEqual(store.getBaseline("support-quality"), candidate);
});

test("store rejects duplicate run IDs and invalid baselines", async () => {
  const store = new InMemoryEvaluationRunStore();
  const report = await makeReport();
  store.save(report, "run-1");
  assert.throws(() => store.save(report, ""), EvaluationRunStoreError);
  assert.throws(() => store.save(report, "run-1"), EvaluationRunStoreError);
  assert.throws(() => store.setBaseline("other-suite", "run-1"), EvaluationRunStoreError);
  assert.throws(() => store.setBaseline("support-quality", "missing"), EvaluationRunStoreError);
});

test("SQLite store recovers runs and baseline after reopening", async () => {
  const directory = mkdtempSync(join(tmpdir(), "agentops-evaluation-"));
  const filename = join(directory, "runs.sqlite3");
  const report = await makeReport();
  const database = new Database(filename);
  const store = new SqliteEvaluationRunStore(database, () => 1_800_000_000_123);
  assert.throws(() => store.save(report, ""), EvaluationRunStoreError);
  const saved = store.save(report, "durable-1");
  store.setBaseline("support-quality", "durable-1");
  database.close();

  const reopenedDatabase = new Database(filename);
  const reopened = new SqliteEvaluationRunStore(reopenedDatabase);
  assert.deepEqual(reopened.get("durable-1"), saved);
  assert.deepEqual(reopened.getBaseline("support-quality"), saved);
  const replacement = reopened.save(report, "durable-2");
  reopened.setBaseline("support-quality", "durable-2");
  assert.deepEqual(reopened.getBaseline("support-quality"), replacement);
  assert.throws(() => reopened.save(report, "durable-2"), EvaluationRunStoreError);
  reopenedDatabase.close();
  rmSync(directory, { recursive: true, force: true });
});

test("SQLite baseline update is suite-bound", async () => {
  const database = new Database(":memory:");
  const store = new SqliteEvaluationRunStore(database);
  store.save(await makeReport(), "run-1");
  assert.throws(() => store.setBaseline("different-suite", "run-1"), EvaluationRunStoreError);
  assert.equal(store.getBaseline("different-suite"), undefined);
  database.close();
});
