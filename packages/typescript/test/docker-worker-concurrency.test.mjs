import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { DockerWorker } from "../dist/index.js";

test("maxConcurrentWorkers serializes container launches", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "agentops-docker-concurrency-"));
  try {
    const executable = path.join(directory, "docker-stub");
    await writeFile(executable, `#!/usr/bin/env node
if (process.argv[2] === "run") {
  let input = "";
  process.stdin.on("data", d => input += d);
  process.stdin.on("end", () => {
    const request = JSON.parse(input);
    setTimeout(() => process.stdout.write(JSON.stringify({
      protocol_version: 1, request_id: request.request_id, result: request.input,
    }) + "\\n"), 150);
  });
}
`);
    await chmod(executable, 0o755);
    const worker = new DockerWorker("example/worker:latest", {
      dockerExecutable: executable, maxConcurrentWorkers: 1,
    });
    const started = Date.now();
    const results = await Promise.all([
      worker.execute("tool", { value: 1 }),
      worker.execute("tool", { value: 2 }),
    ]);
    assert.deepEqual(results, [{ value: 1 }, { value: 2 }]);
    assert.ok(Date.now() - started >= 250);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("maxConcurrentWorkers must be positive", () => {
  assert.throws(() => new DockerWorker("example/worker:latest", { maxConcurrentWorkers: 0 }), TypeError);
});
