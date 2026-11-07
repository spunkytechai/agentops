import test from "node:test";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  AgentAlreadyRegisteredError,
  AgentDefinition,
  AgentNotFoundError,
  AgentRegistry,
  SqliteAgentRegistryStore,
} from "../dist/index.js";

const require = createRequire(import.meta.url);
const Database = require("better-sqlite3");

test("agent versions survive registry restart", () => {
  const directory = mkdtempSync(join(tmpdir(), "agentops-registry-"));
  const path = join(directory, "agents.sqlite3");
  const firstDb = new Database(path);
  try {
    const first = new AgentRegistry({ store: new SqliteAgentRegistryStore(firstDb) });
    const agent = new AgentDefinition({
      agentId: "support.assistant",
      version: "1.0.0",
      description: "Support agent",
      tools: ["knowledge.search", "ticket.create"],
    });
    first.register(agent);
    firstDb.close();

    const restartedDb = new Database(path);
    try {
      const restarted = new AgentRegistry({ store: new SqliteAgentRegistryStore(restartedDb) });
      assert.deepEqual(restarted.get("support.assistant", "1.0.0"), agent);
      assert.deepEqual(restarted.list(), [agent]);
    } finally {
      restartedDb.close();
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("duplicate version is rejected across independent registry connections", () => {
  const directory = mkdtempSync(join(tmpdir(), "agentops-registry-"));
  const path = join(directory, "agents.sqlite3");
  const firstDb = new Database(path);
  const secondDb = new Database(path);
  try {
    const first = new AgentRegistry({ store: new SqliteAgentRegistryStore(firstDb) });
    const second = new AgentRegistry({ store: new SqliteAgentRegistryStore(secondDb) });
    const agent = new AgentDefinition({ agentId: "support.assistant", version: "1.0.0" });
    first.register(agent);
    assert.throws(() => second.register(agent), AgentAlreadyRegisteredError);
  } finally {
    firstDb.close();
    secondDb.close();
    rmSync(directory, { recursive: true, force: true });
  }
});

test("lists persisted agents in deterministic order and supports exact filtering", () => {
  const db = new Database(":memory:");
  const registry = new AgentRegistry({ store: new SqliteAgentRegistryStore(db) });
  registry.register(new AgentDefinition({ agentId: "zeta.agent", version: "1.0.0" }));
  registry.register(new AgentDefinition({ agentId: "alpha.agent", version: "2.0.0" }));
  registry.register(new AgentDefinition({ agentId: "alpha.agent", version: "1.0.0" }));
  assert.deepEqual(
    registry.list().map((item) => [item.agentId, item.version]),
    [["alpha.agent", "1.0.0"], ["alpha.agent", "2.0.0"], ["zeta.agent", "1.0.0"]],
  );
  assert.deepEqual(
    registry.list("alpha.agent").map((item) => item.version),
    ["1.0.0", "2.0.0"],
  );
  db.close();
});

test("missing persisted agent throws AgentNotFoundError", () => {
  const db = new Database(":memory:");
  const registry = new AgentRegistry({ store: new SqliteAgentRegistryStore(db) });
  assert.throws(() => registry.get("missing.agent", "1.0.0"), AgentNotFoundError);
  db.close();
});

test("shared conformance fixture round-trips through SQLite", () => {
  const fixture = JSON.parse(
    readFileSync("../../conformance/fixtures/agents.json", "utf8"),
  );
  const db = new Database(":memory:");
  const registry = new AgentRegistry({ store: new SqliteAgentRegistryStore(db) });
  for (const item of fixture.agents) {
    registry.register(new AgentDefinition({
      agentId: item.agent_id,
      version: item.version,
      description: item.description,
      tools: item.tools,
    }));
  }
  assert.deepEqual(
    registry.list().map((agent) => ({
      agent_id: agent.agentId,
      version: agent.version,
      description: agent.description,
      tools: [...agent.tools],
    })),
    fixture.agents,
  );
  db.close();
});
