import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { WorkerProcess, WorkerExecutionError } from "../dist/index.js";

test("executes a versioned JSONL request and returns its result", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e",
    "let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const r=JSON.parse(s);process.stdout.write(JSON.stringify({protocol_version:1,request_id:r.request_id,result:r.input})+'\\n')})"
  ]);
  assert.deepEqual(await worker.execute("math.add", { value: 42 }, { requestId: "req-1" }), { value: 42 });
});

test("rejects non-finite numbers instead of silently converting them to null", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e",
    "let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const r=JSON.parse(s);process.stdout.write(JSON.stringify({protocol_version:1,request_id:r.request_id,result:r.input})+'\\n')})"
  ]);
  await assert.rejects(worker.execute("tool", { amount: Number.NaN }), WorkerExecutionError);
});

test("rejects undefined values instead of silently omitting protocol fields", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e",
    "let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const r=JSON.parse(s);process.stdout.write(JSON.stringify({protocol_version:1,request_id:r.request_id,result:r.input})+'\\n')})"
  ]);
  await assert.rejects(worker.execute("tool", { value: undefined }), WorkerExecutionError);
});

test("rejects oversized input before spawning", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e", "process.exit(99)"], { maxInputBytes: 32 });
  await assert.rejects(worker.execute("tool", { payload: "x".repeat(100) }), WorkerExecutionError);
});

test("kills worker when output exceeds its byte budget", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e", "process.stdout.write('x'.repeat(4096))"], { maxOutputBytes: 128 });
  await assert.rejects(worker.execute("tool", {}), WorkerExecutionError);
});

test("terminates worker at its deadline", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e", "setTimeout(()=>{},5000)"], { timeoutMs: 50 });
  await assert.rejects(worker.execute("tool", {}), WorkerExecutionError);
});

test("rejects protocol version and request ID mismatch", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e",
    "process.stdin.resume();process.stdin.on('end',()=>process.stdout.write(JSON.stringify({protocol_version:99,request_id:'wrong',result:1})+'\\n'))"
  ]);
  await assert.rejects(worker.execute("tool", {}, { requestId: "expected" }), WorkerExecutionError);
});

test("timeout terminates worker descendants on POSIX", { skip: process.platform === "win32" }, async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "agentops-worker-tree-"));
  const marker = path.join(directory, "orphan-was-alive");
  const child = `setTimeout(() => require("node:fs").writeFileSync(${JSON.stringify(marker)}, "alive"), 400)`;
  const parent = `require("node:child_process").spawn(process.execPath, ["-e", ${JSON.stringify(child)}]); setTimeout(() => {}, 5000)`;
  try {
    const worker = new WorkerProcess(process.execPath, ["-e", parent], { timeoutMs: 100 });
    await assert.rejects(worker.execute("tool", {}), WorkerExecutionError);
    await new Promise(resolve => setTimeout(resolve, 600));
    assert.equal(existsSync(marker), false, "worker descendant survived timeout");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
