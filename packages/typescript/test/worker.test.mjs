import test from "node:test";
import assert from "node:assert/strict";
import { WorkerProcess, WorkerExecutionError } from "../dist/index.js";

test("executes a versioned JSONL request and returns its result", async () => {
  const worker = new WorkerProcess(process.execPath, ["-e",
    "let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const r=JSON.parse(s);process.stdout.write(JSON.stringify({protocol_version:1,request_id:r.request_id,result:r.input})+'\\n')})"
  ]);
  assert.deepEqual(await worker.execute("math.add", { value: 42 }, { requestId: "req-1" }), { value: 42 });
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
