import unittest

from agentops import InMemoryRecorder, PolicyRule, ToolExecutor, ToolPolicy, TraceContext


class TraceContextTests(unittest.TestCase):
    def test_trace_context_validates_w3c_identifier_width_and_hex(self):
        with self.assertRaises(ValueError):
            TraceContext(trace_id="short", span_id="0123456789abcdef")

    def test_executor_propagates_trace_and_parent_context_to_lifecycle_events(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"math.add"})), recorder)
        context = TraceContext(
            trace_id="0123456789abcdef0123456789abcdef",
            span_id="0123456789abcdef",
            parent_span_id="fedcba9876543210",
        )
        self.assertEqual(
            executor.execute("math.add", lambda: 7, run_id="trace-run", trace_context=context),
            7,
        )
        self.assertEqual(len(recorder.events), 2)
        for event in recorder.events:
            self.assertEqual(event.trace_id, context.trace_id)
            self.assertEqual(event.span_id, context.span_id)
            self.assertEqual(event.parent_span_id, context.parent_span_id)

    def test_executor_creates_valid_trace_context_when_not_supplied(self):
        recorder = InMemoryRecorder()
        executor = ToolExecutor(ToolPolicy(frozenset({"math.add"})), recorder)
        executor.execute("math.add", lambda: 7, run_id="generated-trace")
        event = recorder.events[0]
        self.assertRegex(event.trace_id, r"^[0-9a-f]{32}$")
        self.assertRegex(event.span_id, r"^[0-9a-f]{16}$")
        self.assertIsNone(event.parent_span_id)

    def test_child_context_keeps_trace_id_and_links_parent_span(self):
        parent = TraceContext.create()
        child = TraceContext.create(parent)
        self.assertEqual(child.trace_id, parent.trace_id)
        self.assertEqual(child.parent_span_id, parent.span_id)
        self.assertNotEqual(child.span_id, parent.span_id)
