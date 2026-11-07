import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { actionFingerprint } from "../dist/index.js";

const fixturePath = new URL("../../../conformance/fixtures/action-fingerprint.json", import.meta.url);
const fixture = JSON.parse(readFileSync(fileURLToPath(fixturePath), "utf8"));

test("action fingerprint matches the shared Python/TypeScript fixture", () => {
  assert.equal(actionFingerprint(fixture.action), fixture.sha256);
});

test("object key order does not change the action fingerprint", () => {
  const reordered = {
    currency: fixture.action.currency,
    order_id: fixture.action.order_id,
    amount: fixture.action.amount,
  };
  assert.equal(actionFingerprint(reordered), fixture.sha256);
});

test("unsupported floating point values are rejected", () => {
  assert.throws(() => actionFingerprint({ amount: 2.5 }), TypeError);
});

test("unpaired Unicode surrogates are rejected", () => {
  assert.throws(() => actionFingerprint({ invalid: "\\ud800" }), TypeError);
});
