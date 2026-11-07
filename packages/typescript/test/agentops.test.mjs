import test from "node:test";
import assert from "node:assert/strict";
import { InMemoryRecorder, PolicyDeniedError, ToolExecutor, ToolPolicy } from "../dist/index.js";

test("policy denies tools by default", () => {
  assert.equal(new ToolPolicy().evaluate("filesystem.read").allowed, false);
});

test("explicit deny overrides allow", () => {
  const policy = new ToolPolicy({
    allowedTools: ["payments.refund"],
    deniedTools: ["payments.refund"],
  });
  assert.equal(policy.evaluate("payments.refund").reason, "explicitly denied");
});

test("executor runs allowed tools and records lifecycle", async () => {
  const recorder = new InMemoryRecorder();
  const executor = new ToolExecutor(new ToolPolicy({ allowedTools: ["math.add"] }), recorder);
  assert.equal(await executor.execute("math.add", () => 5, "run-1"), 5);
  assert.deepEqual(recorder.events.map((event) => event.type), ["tool.started", "tool.succeeded"]);
  assert.equal(recorder.events[0].runId, "run-1");
});

test("denied tools are never invoked or recorded", async () => {
  const recorder = new InMemoryRecorder();
  const executor = new ToolExecutor(new ToolPolicy(), recorder);
  let invoked = false;
  await assert.rejects(
    executor.execute("dangerous.delete", () => { invoked = true; }),
    PolicyDeniedError,
  );
  assert.equal(invoked, false);
  assert.deepEqual(recorder.events, []);
});

test("failures are recorded and rethrown", async () => {
  const recorder = new InMemoryRecorder();
  const executor = new ToolExecutor(new ToolPolicy({ allowedTools: ["network.fetch"] }), recorder);
  await assert.rejects(
    executor.execute("network.fetch", () => { throw new TypeError("offline"); }),
    /offline/,
  );
  assert.equal(recorder.events.at(-1).type, "tool.failed");
  assert.equal(recorder.events.at(-1).errorType, "TypeError");
});
