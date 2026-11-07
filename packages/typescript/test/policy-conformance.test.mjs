import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PolicyRule, ToolPolicy } from "../dist/index.js";

const fixturePath = new URL("../../../conformance/fixtures/policy.json", import.meta.url);
const fixture = JSON.parse(readFileSync(fileURLToPath(fixturePath), "utf8"));

test("policy snapshots mutable constructor inputs consistently with shared fixtures", () => {
  const allowedTools = [...fixture.initial.allowedTools];
  const deniedTools = [...fixture.initial.deniedTools];
  const rules = fixture.initial.rules.map((rule) => new PolicyRule({
    principalId: rule.principalId,
    toolName: rule.toolName,
    effect: rule.effect,
  }));
  const policy = new ToolPolicy({ allowedTools, deniedTools, rules });

  allowedTools.push(fixture.mutations.addAllowedTool);
  deniedTools.splice(deniedTools.indexOf(fixture.mutations.removeDeniedTool), 1);
  rules.push(new PolicyRule(fixture.mutations.addRule));

  const actual = fixture.expected.map((item) =>
    policy.evaluate(item.toolName, item.principalId)
  );
  assert.deepEqual(
    actual.map(({ allowed, reason }) => ({ allowed, reason })),
    fixture.expected.map(({ allowed, reason }) => ({ allowed, reason })),
  );
});
