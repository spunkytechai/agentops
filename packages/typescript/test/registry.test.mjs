import test from "node:test";
import assert from "node:assert/strict";
import {
  AgentAlreadyRegisteredError,
  AgentDefinition,
  AgentNotFoundError,
  AgentRegistry,
} from "../dist/index.js";

test("registers and retrieves a versioned agent", () => {
  const registry = new AgentRegistry();
  const agent = new AgentDefinition({
    agentId: "support.assistant",
    version: "1.0.0",
    description: "Customer support agent",
    tools: ["knowledge.search", "ticket.create"],
  });
  registry.register(agent);
  assert.deepEqual(registry.get("support.assistant", "1.0.0"), agent);
});

test("rejects duplicate agent versions", () => {
  const registry = new AgentRegistry();
  const agent = new AgentDefinition({ agentId: "research.agent", version: "1.0.0" });
  registry.register(agent);
  assert.throws(() => registry.register(agent), AgentAlreadyRegisteredError);
});

test("lists versions in deterministic order", () => {
  const registry = new AgentRegistry();
  registry.register(new AgentDefinition({ agentId: "research.agent", version: "2.0.0" }));
  registry.register(new AgentDefinition({ agentId: "research.agent", version: "1.0.0" }));
  assert.deepEqual(
    registry.list("research.agent").map((agent) => agent.version),
    ["1.0.0", "2.0.0"],
  );
});

test("throws when an agent version does not exist", () => {
  assert.throws(
    () => new AgentRegistry().get("missing.agent", "1.0.0"),
    AgentNotFoundError,
  );
});

test("rejects invalid definitions and duplicate tool identifiers", () => {
  assert.throws(() => new AgentDefinition({ agentId: " ", version: "1.0.0" }), TypeError);
  assert.throws(
    () => new AgentDefinition({ agentId: "valid.agent", version: "1.0.0", tools: ["search", "search"] }),
    TypeError,
  );
});
