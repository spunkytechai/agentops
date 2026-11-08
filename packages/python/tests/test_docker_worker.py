import json
import threading
import time
from unittest.mock import patch
import os
import sys
import tempfile
import unittest
from pathlib import Path

from agentops import DockerWorker, WorkerExecutionError


class DockerWorkerTests(unittest.TestCase):
    def _docker_stub(self, directory: str, *, sleep: bool = False) -> tuple[str, str]:
        log = str(Path(directory) / "docker-args.jsonl")
        script = Path(directory) / "docker-stub"
        script.write_text(
            "#!" + sys.executable + "\n"
            "import json,sys,time\n"
            f"log={log!r}\n"
            "with open(log,'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "if len(sys.argv)>2 and sys.argv[1]=='run':\n"
            + (" time.sleep(5)\n" if sleep else
               " r=json.loads(sys.stdin.readline()); print(json.dumps({'protocol_version':1,'request_id':r['request_id'],'result':{'ok':True}}))\n")
            + "sys.exit(0)\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return str(script), log

    def test_runs_worker_with_hardened_defaults_and_cleans_up_container(self):
        with tempfile.TemporaryDirectory() as directory:
            docker, log = self._docker_stub(directory)
            worker = DockerWorker("example/worker:1.0", docker_executable=docker)
            self.assertEqual(worker.execute("report.build", {"id": 7}), {"ok": True})
            calls = [json.loads(line) for line in Path(log).read_text().splitlines()]
            run_args, cleanup_args = calls
            joined = " ".join(run_args)
            for flag in ("--network=none", "--read-only", "--cap-drop=ALL",
                         "--security-opt=no-new-privileges", "--user=65532:65532",
                         "--memory=268435456", "--memory-swap=268435456",
                         "--cpus=1", "--pids-limit=64"):
                self.assertIn(flag, joined)
            self.assertTrue(any(arg.startswith("--tmpfs=/tmp:") for arg in run_args))
            self.assertIn("--pull=never", run_args)
            self.assertEqual(run_args[-1], "example/worker:1.0")
            self.assertEqual(cleanup_args[0:2], ["rm", "--force"])
            self.assertTrue(cleanup_args[2].startswith("agentops-worker-"))

    def test_applies_configured_resource_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            docker, log = self._docker_stub(directory)
            worker = DockerWorker(
                "example/worker:latest", docker_executable=docker,
                memory_limit_bytes=536870912, cpu_limit=1.5,
                pids_limit=32, tmpfs_size_bytes=8388608,
            )
            worker.execute("tool", {})
            args = json.loads(Path(log).read_text().splitlines()[0])
            joined = " ".join(args)
            self.assertIn("--memory=536870912", joined)
            self.assertIn("--memory-swap=536870912", joined)
            self.assertIn("--cpus=1.5", joined)
            self.assertIn("--pids-limit=32", joined)
            self.assertIn("size=8388608", joined)

    def test_rejects_unsafe_image_and_resource_configuration(self):
        with self.assertRaises(ValueError):
            DockerWorker("--privileged", docker_executable="docker")
        with self.assertRaises(ValueError):
            DockerWorker("example/worker", memory_limit_bytes=0)
        with self.assertRaises(ValueError):
            DockerWorker("example/worker", cpu_limit=0)
        with self.assertRaises(ValueError):
            DockerWorker("example/worker", pids_limit=-1)
        with self.assertRaises(ValueError):
            DockerWorker("example/worker\x00")
        with self.assertRaises(ValueError):
            DockerWorker("example/worker", docker_executable="docker\x00")

    def test_slot_wait_consumes_the_same_overall_deadline_as_execution(self):
        worker = DockerWorker("example/worker:latest", timeout_seconds=0.3, max_concurrent_workers=1)
        started = threading.Event()

        def fake_execute(tool_name, input, **kwargs):
            if not started.is_set():
                started.set()
                time.sleep(0.15)
            return {"ok": True}

        with patch("agentops.docker_worker.WorkerProcess") as process:
            process.return_value.execute.side_effect = fake_execute
            first = threading.Thread(target=lambda: worker.execute("first", {}))
            first.start()
            self.assertTrue(started.wait(timeout=1))
            time.sleep(0.05)
            self.assertEqual(worker.execute("second", {}), {"ok": True})
            first.join(timeout=1)
            self.assertFalse(first.is_alive())
            timeouts = [
                call.kwargs["timeout_seconds"] for call in process.call_args_list
            ]
        self.assertEqual(len(timeouts), 2)
        self.assertGreater(timeouts[0], 0.25)
        self.assertLess(timeouts[1], timeouts[0] - 0.04)

    def test_cleans_up_container_after_worker_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            docker, log = self._docker_stub(directory, sleep=True)
            worker = DockerWorker("example/worker:latest", docker_executable=docker, timeout_seconds=0.05)
            with self.assertRaises(WorkerExecutionError):
                worker.execute("tool", {})
            calls = [json.loads(line) for line in Path(log).read_text().splitlines()]
            self.assertTrue(any(call[:2] == ["rm", "--force"] for call in calls))


if __name__ == "__main__":
    unittest.main()
