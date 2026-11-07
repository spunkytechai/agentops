import unittest

from agentops import InMemoryRecorder, PolicyDeniedError, ToolExecutor, ToolPolicy


class ToolPolicyTests(unittest.TestCase):
    def test_deny_by_default(self):
        self.assertFalse(ToolPolicy().evaluate("filesystem.read").allowed)

    def test_deny_overrides_allow(self):
        policy = ToolPolicy(frozenset({"payments.refund"}), frozenset({"payments.refund"}))
        self.assertFalse(policy.evaluate("payments.refund").allowed)

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            ToolPolicy().evaluate(" ")


class ToolExecutorTests(unittest.TestCase):
    def test_allowed_execution_records_lifecycle(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"math.add"})), recorder)
        self.assertEqual(executor.execute("math.add", lambda: 5, run_id="run-1"), 5)
        self.assertEqual([e.event_type for e in recorder.events],
                         ["tool.started", "tool.succeeded"])
        self.assertTrue(all(e.run_id == "run-1" for e in recorder.events))

    def test_denied_operation_is_never_invoked(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(), recorder)
        invoked = False
        def operation():
            nonlocal invoked
            invoked = True
        with self.assertRaises(PolicyDeniedError):
            executor.execute("dangerous.delete", operation)
        self.assertFalse(invoked)
        self.assertEqual(recorder.events, ())

    def test_failure_is_recorded_and_reraised(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"network.fetch"})), recorder)
        def fail():
            raise RuntimeError("upstream unavailable")
        with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
            executor.execute("network.fetch", fail)
        self.assertEqual(recorder.events[-1].event_type, "tool.failed")
        self.assertEqual(recorder.events[-1].error_type, "RuntimeError")


if __name__ == "__main__":
    unittest.main()
