import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { DockerWorker, WorkerExecutionError } from "../dist/index.js";
import { WorkerProcess } from "../dist/worker.js";

async function createDockerStub(directory, { sleep = false } = {}) {
  const log = path.join(directory, "docker-args.jsonl");
  const executable = path.join(directory, "docker-stub");
  const source = `#!/usr/bin/env node
import fs from "node:fs";
const log = ${JSON.stringify(log)};
fs.appendFileSync(log, JSON.stringify(process.argv.slice(2)) + "\\n");
if (process.argv[2] === "run") {
  ${sleep ? "setTimeout(() => {}, 5000);" : `let input = ""; process.stdin.on("data", d => input += d); process.stdin.on("end", () => { const req = JSON.parse(input); process.stdout.write(JSON.stringify({protocol_version:1,request_id:req.request_id,result:{ok:true}}) + "\\n"); });`}
}
`;
  await writeFile(executable, source);
  await chmod(executable, 0o755);
  return { executable, log };
}

test("runs with hardened Docker defaults and removes the named container", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "agentops-docker-"));
  try {
    const { executable, log } = await createDockerStub(directory);
    const worker = new DockerWorker("example/worker:1.0", { dockerExecutable: executable });
    assert.deepEqual(await worker.execute("report.build", { id: 7 }), { ok: true });
    const calls = (await readFile(log, "utf8")).trim().split("\n").map(JSON.parse);
    const args = calls[0].join(" ");
    for (const flag of ["--network=none", "--read-only", "--cap-drop=ALL",
      "--security-opt=no-new-privileges", "--user=65532:65532",
      "--memory=268435456", "--memory-swap=268435456", "--cpus=1", "--pids-limit=64"]) {
      assert.ok(args.includes(flag), flag);
    }
    assert.ok(calls[0].some(arg => arg.startsWith("--tmpfs=/tmp:")));
    assert.ok(calls[0].includes("--pull=never"));
    assert.equal(calls[0].at(-1), "example/worker:1.0");
    assert.deepEqual(calls[1].slice(0, 2), ["rm", "--force"]);
    assert.match(calls[1][2], /^agentops-worker-/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("applies configured resource budgets", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "agentops-docker-"));
  try {
    const { executable, log } = await createDockerStub(directory);
    const worker = new DockerWorker("example/worker:latest", {
      dockerExecutable: executable, memoryLimitBytes: 536870912,
      cpuLimit: 1.5, pidsLimit: 32, tmpfsSizeBytes: 8388608,
    });
    await worker.execute("tool", {});
    const args = JSON.parse((await readFile(log, "utf8")).trim().split("\n")[0]).join(" ");
    for (const flag of ["--memory=536870912", "--memory-swap=536870912",
      "--cpus=1.5", "--pids-limit=32", "size=8388608"]) assert.ok(args.includes(flag), flag);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("rejects unsafe image references and resource configurations", () => {
  assert.throws(() => new DockerWorker("--privileged"), TypeError);
  assert.throws(() => new DockerWorker("example/worker", { memoryLimitBytes: 0 }), TypeError);
  assert.throws(() => new DockerWorker("example/worker", { cpuLimit: 0 }), TypeError);
  assert.throws(() => new DockerWorker("example/worker", { pidsLimit: -1 }), TypeError);
  assert.throws(() => new DockerWorker("example/worker\0"), TypeError);
  assert.throws(() => new DockerWorker("example/worker", { dockerExecutable: "docker\0" }), TypeError);
});

test("slot wait consumes the same overall deadline as execution", async () => {
  const original = WorkerProcess.prototype.execute;
  const observedTimeouts = [];
  let signalStarted;
  const started = new Promise(resolve => { signalStarted = resolve; });
  WorkerProcess.prototype.execute = async function () {
    observedTimeouts.push(this.timeoutMs);
    if (observedTimeouts.length === 1) {
      signalStarted();
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    return { ok: true };
  };
  try {
    const worker = new DockerWorker("example/worker:latest", {
      dockerExecutable: process.execPath, timeoutMs: 300, maxConcurrentWorkers: 1,
    });
    const first = worker.execute("first", {});
    await started;
    await new Promise(resolve => setTimeout(resolve, 50));
    const second = worker.execute("second", {});
    assert.deepEqual(await Promise.all([first, second]), [{ ok: true }, { ok: true }]);
    assert.equal(observedTimeouts.length, 2);
    assert.ok(observedTimeouts[1] < observedTimeouts[0] - 40);
  } finally {
    WorkerProcess.prototype.execute = original;
  }
});

test("removes the container after a worker deadline", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "agentops-docker-"));
  try {
    const { executable, log } = await createDockerStub(directory, { sleep: true });
    const worker = new DockerWorker("example/worker:latest", { dockerExecutable: executable, timeoutMs: 50 });
    await assert.rejects(worker.execute("tool", {}), WorkerExecutionError);
    const calls = (await readFile(log, "utf8")).trim().split("\n").map(JSON.parse);
    assert.ok(calls.some(call => call[0] === "rm" && call[1] === "--force"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("executes inside a real hardened Docker container", {
  skip: process.env.AGENTOPS_DOCKER_INTEGRATION !== "1",
}, async () => {
  const worker = new DockerWorker("agentops-example-worker:ci");
  assert.deepEqual(await worker.execute("identity.echo", { value: "container" }), {
    echo: { value: "container" },
  });
});
