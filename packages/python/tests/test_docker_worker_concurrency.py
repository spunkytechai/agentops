import json
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agentops import DockerWorker


class DockerWorkerConcurrencyTests(unittest.TestCase):
    def test_max_concurrent_workers_serializes_container_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "docker-stub"
            script.write_text(
                "#!" + sys.executable + "\n"
                "import json,sys,time\n"
                "if sys.argv[1] == 'run':\n"
                " r=json.loads(sys.stdin.readline()); time.sleep(0.15); "
                "print(json.dumps({'protocol_version':1,'request_id':r['request_id'],'result':r['input']}))\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            worker = DockerWorker("example/worker:latest", docker_executable=str(script), max_concurrent_workers=1)
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda value: worker.execute("tool", value), ({"v": 1}, {"v": 2})))
            self.assertEqual(results, [{"v": 1}, {"v": 2}])
            self.assertGreaterEqual(time.monotonic() - started, 0.25)

    def test_max_concurrent_workers_must_be_positive(self):
        with self.assertRaises(ValueError):
            DockerWorker("example/worker:latest", max_concurrent_workers=0)


if __name__ == "__main__":
    unittest.main()
