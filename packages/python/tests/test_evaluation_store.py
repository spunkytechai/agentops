import tempfile
import unittest
from pathlib import Path

from agentops import (
    EvaluationCase,
    EvaluationRunStoreError,
    EvaluationSuite,
    InMemoryEvaluationRunStore,
    SqliteEvaluationRunStore,
)


class EvaluationRunStoreTests(unittest.TestCase):
    def setUp(self):
        self.report = EvaluationSuite(
            "support-quality",
            (EvaluationCase("greeting", "hello", "hello"),),
        ).run(lambda value: value)

    def test_in_memory_store_saves_runs_and_moves_baseline(self):
        store = InMemoryEvaluationRunStore(clock=lambda: 1_800_000_000_000)
        first = store.save(self.report, run_id="run-1")
        self.assertEqual(first.run_id, "run-1")
        self.assertEqual(first.created_at_ms, 1_800_000_000_000)
        self.assertEqual(store.get("run-1"), first)
        store.set_baseline("support-quality", "run-1")
        self.assertEqual(store.get_baseline("support-quality"), first)

        candidate = store.save(self.report, run_id="run-2")
        store.set_baseline("support-quality", "run-2")
        self.assertEqual(store.get_baseline("support-quality"), candidate)

    def test_store_rejects_duplicate_run_ids_and_invalid_baselines(self):
        store = InMemoryEvaluationRunStore()
        store.save(self.report, run_id="run-1")
        with self.assertRaises(EvaluationRunStoreError):
            store.save(self.report, run_id="")
        with self.assertRaises(EvaluationRunStoreError):
            store.save(self.report, run_id="run-1")
        with self.assertRaises(EvaluationRunStoreError):
            store.set_baseline("other-suite", "run-1")
        with self.assertRaises(EvaluationRunStoreError):
            store.set_baseline("support-quality", "missing")

    def test_sqlite_store_recovers_runs_and_baseline_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evaluation.sqlite3"
            store = SqliteEvaluationRunStore(database, clock=lambda: 1_800_000_000_123)
            with self.assertRaises(EvaluationRunStoreError):
                store.save(self.report, run_id="")
            saved = store.save(self.report, run_id="durable-1")
            store.set_baseline("support-quality", "durable-1")
            store.close()

            reopened = SqliteEvaluationRunStore(database)
            self.assertEqual(reopened.get("durable-1"), saved)
            self.assertEqual(reopened.get_baseline("support-quality"), saved)
            replacement = reopened.save(self.report, run_id="durable-2")
            reopened.set_baseline("support-quality", "durable-2")
            self.assertEqual(reopened.get_baseline("support-quality"), replacement)
            with self.assertRaises(EvaluationRunStoreError):
                reopened.save(self.report, run_id="durable-2")
            reopened.close()

    def test_sqlite_baseline_update_is_suite_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteEvaluationRunStore(Path(directory) / "evaluation.sqlite3")
            store.save(self.report, run_id="run-1")
            with self.assertRaises(EvaluationRunStoreError):
                store.set_baseline("different-suite", "run-1")
            self.assertIsNone(store.get_baseline("different-suite"))
            store.close()


if __name__ == "__main__":
    unittest.main()
