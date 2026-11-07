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


class ScopedPolicyTests(unittest.TestCase):
    def test_principal_scoped_allow_only_matches_that_principal(self):
        from agentops import PolicyRule
        policy = ToolPolicy(rules=(PolicyRule("analyst", "reports.read", "allow"),))
        self.assertTrue(policy.evaluate("reports.read", principal_id="analyst").allowed)
        self.assertFalse(policy.evaluate("reports.read", principal_id="operator").allowed)
        self.assertFalse(policy.evaluate("reports.read").allowed)

    def test_principal_scoped_deny_overrides_global_allow(self):
        from agentops import PolicyRule
        policy = ToolPolicy(
            allowed_tools=frozenset({"payments.refund"}),
            rules=(PolicyRule("intern", "payments.refund", "deny"),),
        )
        self.assertFalse(policy.evaluate("payments.refund", principal_id="intern").allowed)
        self.assertTrue(policy.evaluate("payments.refund", principal_id="finance").allowed)

    def test_invalid_policy_rule_is_rejected(self):
        from agentops import PolicyRule
        with self.assertRaises(ValueError):
            PolicyRule(" ", "reports.read", "allow")
        with self.assertRaises(ValueError):
            PolicyRule("analyst", "reports.read", "unknown")




class AsyncToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_execution_records_lifecycle(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"async.lookup"})), recorder)

        async def operation():
            return {"value": 42}

        result = await executor.execute_async("async.lookup", operation, run_id="async-1")
        self.assertEqual(result, {"value": 42})
        self.assertEqual(
            [event.event_type for event in recorder.events],
            ["tool.started", "tool.succeeded"],
        )

    async def test_timeout_cancels_operation_and_records_failure(self):
        import asyncio
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"async.wait"})), recorder)
        cancelled = asyncio.Event()

        async def operation():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        from agentops import ToolExecutionTimeoutError
        with self.assertRaises(ToolExecutionTimeoutError):
            await executor.execute_async("async.wait", operation, timeout_seconds=0.01)

        self.assertTrue(cancelled.is_set())
        self.assertEqual(recorder.events[-1].event_type, "tool.failed")
        self.assertEqual(recorder.events[-1].error_type, "ToolExecutionTimeoutError")

    async def test_invalid_timeout_is_rejected_before_execution(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"async.wait"})), recorder)
        with self.assertRaises(ValueError):
            await executor.execute_async("async.wait", lambda: None, timeout_seconds=0)
        self.assertEqual(recorder.events, ())
