import test from "node:test";
import assert from "node:assert/strict";
import { InMemoryRecorder, ToolExecutor, ToolPolicy, TraceContext } from "../dist/index.js";

test("TraceContext validates W3C trace and span identifier formats", () => {
  assert.throws(
    () => new TraceContext({ traceId: "short", spanId: "0123456789abcdef" }),
    /traceId must be 32 lowercase hexadecimal characters/,
  );
});

test("executor propagates trace and parent span context to lifecycle events", async () => {
  const recorder = new InMemoryRecorder();
  const executor = new ToolExecutor(new ToolPolicy({ allowedTools: ["math.add"] }), recorder);
  const context = new TraceContext({
    traceId: "0123456789abcdef0123456789abcdef",
    spanId: "0123456789abcdef",
    parentSpanId: "fedcba9876543210",
  });
  assert.equal(
    await executor.execute("math.add", async () => 7, "trace-run", { traceContext: context }),
    7,
  );
  assert.equal(recorder.events.length, 2);
  for (const event of recorder.events) {
    assert.equal(event.traceId, context.traceId);
    assert.equal(event.spanId, context.spanId);
    assert.equal(event.parentSpanId, context.parentSpanId);
  }
});

test("executor creates valid trace identifiers when no context is supplied", async () => {
  const recorder = new InMemoryRecorder();
  const executor = new ToolExecutor(new ToolPolicy({ allowedTools: ["math.add"] }), recorder);
  await executor.execute("math.add", async () => 7, "generated-trace");
  assert.match(recorder.events[0].traceId, /^[0-9a-f]{32}$/);
  assert.match(recorder.events[0].spanId, /^[0-9a-f]{16}$/);
  assert.equal(recorder.events[0].parentSpanId, undefined);
});

test("child context keeps trace ID and links the parent span", () => {
  const parent = TraceContext.create();
  const child = TraceContext.create(parent);
  assert.equal(child.traceId, parent.traceId);
  assert.equal(child.parentSpanId, parent.spanId);
  assert.notEqual(child.spanId, parent.spanId);
});
