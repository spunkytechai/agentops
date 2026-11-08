import json
import sys
import unittest

from agentops import WorkerExecutionError, WorkerProcess


class WorkerProcessTests(unittest.TestCase):
    def test_executes_versioned_jsonl_request_and_returns_result(self):
        worker = WorkerProcess([sys.executable, "-c", (
            "import json,sys; r=json.loads(sys.stdin.readline()); "
            "print(json.dumps({'protocol_version':1,'request_id':r['request_id'],'result':r['input']}))"
        )])
        self.assertEqual(worker.execute("math.add", {"value": 42}, request_id="req-1"), {"value": 42})

    def test_rejects_oversized_input_before_starting_process(self):
        worker = WorkerProcess([sys.executable, "-c", "raise SystemExit(99)"], max_input_bytes=32)
        with self.assertRaises(WorkerExecutionError):
            worker.execute("tool", {"payload": "x" * 100})

    def test_rejects_oversized_output_and_terminates_worker(self):
        worker = WorkerProcess([sys.executable, "-c", "print('x' * 4096)"], max_output_bytes=128)
        with self.assertRaises(WorkerExecutionError):
            worker.execute("tool", {})

    def test_enforces_deadline(self):
        worker = WorkerProcess([sys.executable, "-c", "import time; time.sleep(5)"], timeout_seconds=0.05)
        with self.assertRaises(WorkerExecutionError):
            worker.execute("tool", {})

    def test_rejects_mismatched_protocol_response(self):
        worker = WorkerProcess([sys.executable, "-c", (
            "import json; print(json.dumps({'protocol_version':99,'request_id':'wrong','result':1}))"
        )])
        with self.assertRaises(WorkerExecutionError):
            worker.execute("tool", {}, request_id="expected")


if __name__ == "__main__":
    unittest.main()
