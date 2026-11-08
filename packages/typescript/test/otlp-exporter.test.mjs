import test from "node:test";
import assert from "node:assert/strict";
import { OtlpHttpSpanExporter } from "../dist/index.js";

const event = (type, timestamp, extra = {}) => ({
  type, runId: "run-1", toolName: "search", timestamp,
  traceId: "1".repeat(32), spanId: "2".repeat(16), parentSpanId: "3".repeat(16),
  ...extra,
});

test("exports completed lifecycle as OTLP JSON without payload data", async () => {
  const requests = [];
  const exporter = new OtlpHttpSpanExporter("http://collector:4318", (url, headers, body) => {
    requests.push({ url, headers, payload: JSON.parse(body) });
  });
  exporter.record(event("tool.started", "2026-11-08T00:00:00.000Z"));
  exporter.record(event("tool.succeeded", "2026-11-08T00:00:00.125Z", { durationMs: 125 }));
  assert.equal(await exporter.flush(), 1);
  const { url, headers, payload } = requests[0];
  assert.equal(url, "http://collector:4318/v1/traces");
  assert.equal(headers["Content-Type"], "application/json");
  const span = payload.resourceSpans[0].scopeSpans[0].spans[0];
  assert.equal(span.traceId, "1".repeat(32));
  assert.equal(span.spanId, "2".repeat(16));
  assert.equal(span.parentSpanId, "3".repeat(16));
  assert.equal(span.name, "search");
  assert.equal(span.startTimeUnixNano, "1794096000000000000");
  assert.equal(span.endTimeUnixNano, "1794096000125000000");
  assert.equal(span.status.code, 1);
  const encoded = JSON.stringify(payload);
  assert.equal(encoded.includes("prompt"), false);
  assert.equal(encoded.includes("arguments"), false);
  assert.equal(encoded.includes("secret"), false);
});

test("retries a failed HTTP export without losing the batch", async () => {
  let calls = 0;
  const exporter = new OtlpHttpSpanExporter("http://collector:4318", () => {
    calls += 1;
    if (calls === 1) throw new Error("collector unavailable");
  }, { maxQueueSize: 1, maxRetries: 1 });
  exporter.record(event("tool.started", "2026-11-08T00:00:00.000Z"));
  exporter.record(event("tool.succeeded", "2026-11-08T00:00:00.001Z", { durationMs: 1 }));
  assert.equal(await exporter.flush(), 1);
  assert.equal(calls, 2);
});

test("serializes concurrent flushes to preserve FIFO delivery", async () => {
  const sent = [];
  let releaseFirst;
  let firstStarted;
  const firstStartedPromise = new Promise((resolve) => { firstStarted = resolve; });
  const firstGate = new Promise((resolve) => { releaseFirst = resolve; });
  const exporter = new OtlpHttpSpanExporter("http://collector:4318", async (_url, _headers, body) => {
    const spans = JSON.parse(body).resourceSpans[0].scopeSpans[0].spans;
    sent.push(spans[0].attributes.find((item) => item.key === "agentops.run_id").value.stringValue);
    if (sent.length === 1) {
      firstStarted();
      await firstGate;
    }
  }, { maxBatchSize: 1 });

  exporter.record(event("tool.started", "2026-11-08T00:00:00.000Z", { runId: "first" }));
  exporter.record(event("tool.succeeded", "2026-11-08T00:00:00.001Z", { runId: "first" }));
  exporter.record(event("tool.started", "2026-11-08T00:00:00.002Z", { runId: "second", spanId: "4".repeat(16) }));
  exporter.record(event("tool.succeeded", "2026-11-08T00:00:00.003Z", { runId: "second", spanId: "4".repeat(16) }));

  const firstFlush = exporter.flush();
  await firstStartedPromise;
  const secondFlush = exporter.flush();
  await Promise.resolve();
  assert.deepEqual(sent, ["first"]);
  releaseFirst();
  assert.deepEqual(await Promise.all([firstFlush, secondFlush]), [2, 0]);
  assert.deepEqual(sent, ["first", "second"]);
});
