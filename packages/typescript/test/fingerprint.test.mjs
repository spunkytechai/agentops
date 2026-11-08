import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { actionFingerprint, canonicalActionJson } from "../dist/index.js";

const fixturePath = new URL("../../../conformance/fixtures/action-fingerprint.json", import.meta.url);
const fixture = JSON.parse(readFileSync(fileURLToPath(fixturePath), "utf8"));

test("action fingerprint matches the shared Python/TypeScript fixture", () => {
  assert.equal(actionFingerprint(fixture.action), fixture.sha256);
});

test("object key order does not change the action fingerprint", () => {
  const reordered = Object.fromEntries(Object.entries(fixture.action).reverse());
  assert.equal(actionFingerprint(reordered), fixture.sha256);
});

test("unsupported floating point values are rejected", () => {
  assert.throws(() => actionFingerprint({ amount: 2.5 }), TypeError);
});

test("unpaired Unicode surrogates are rejected", () => {
  assert.throws(() => actionFingerprint({ invalid: "\ud800" }), TypeError);
});

test("the __proto__ action key is preserved in canonical JSON", () => {
  const action = JSON.parse('{"__proto__":{"admin":true},"amount":2500}');
  assert.equal(
    canonicalActionJson(action),
    '{"__proto__":{"admin":true},"amount":2500}',
  );
});
