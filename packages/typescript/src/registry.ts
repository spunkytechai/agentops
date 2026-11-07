import type { SqliteDatabase } from "./approvals.js";

export interface AgentDefinitionOptions {
  readonly agentId: string;
  readonly version: string;
  readonly description?: string;
  readonly tools?: readonly string[];
}

function requireText(value: string, field: string): void {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new TypeError(`${field} must be a non-empty string`);
  }
}

/** Immutable, provider-neutral description of one agent version. */
export class AgentDefinition {
  readonly agentId: string;
  readonly version: string;
  readonly description: string;
  readonly tools: readonly string[];

  constructor(options: AgentDefinitionOptions) {
    requireText(options.agentId, "agentId");
    requireText(options.version, "version");
    const description = options.description ?? "";
    if (typeof description !== "string") {
      throw new TypeError("description must be a string");
    }
    const tools = [...(options.tools ?? [])];
    for (const name of tools) requireText(name, "tool name");
    if (new Set(tools).size !== tools.length) {
      throw new TypeError("tool names must be unique");
    }
    this.agentId = options.agentId;
    this.version = options.version;
    this.description = description;
    this.tools = Object.freeze(tools);
    Object.freeze(this);
  }
}

export class AgentAlreadyRegisteredError extends Error {
  constructor(agentId: string, version: string) {
    super(`Agent "${agentId}" version "${version}" is already registered`);
    this.name = "AgentAlreadyRegisteredError";
  }
}

export class AgentNotFoundError extends Error {
  constructor(agentId: string, version: string) {
    super(`Agent "${agentId}" version "${version}" was not found`);
    this.name = "AgentNotFoundError";
  }
}

export interface AgentRegistryStore {
  /** Atomically inserts a new immutable version; false means the key exists. */
  create(agent: AgentDefinition): boolean;
  get(agentId: string, version: string): AgentDefinition | undefined;
  list(agentId?: string): readonly AgentDefinition[];
}

export class InMemoryAgentRegistryStore implements AgentRegistryStore {
  private readonly agents = new Map<string, AgentDefinition>();

  create(agent: AgentDefinition): boolean {
    const key = this.key(agent.agentId, agent.version);
    if (this.agents.has(key)) return false;
    this.agents.set(key, agent);
    return true;
  }

  get(agentId: string, version: string): AgentDefinition | undefined {
    return this.agents.get(this.key(agentId, version));
  }

  list(agentId?: string): readonly AgentDefinition[] {
    return [...this.agents.values()]
      .filter((agent) => agentId === undefined || agent.agentId === agentId)
      .sort((left, right) =>
        (left.agentId < right.agentId ? -1 : left.agentId > right.agentId ? 1 : 0) ||
        (left.version < right.version ? -1 : left.version > right.version ? 1 : 0),
      );
  }

  private key(agentId: string, version: string): string {
    requireText(agentId, "agentId");
    requireText(version, "version");
    return JSON.stringify([agentId, version]);
  }
}

/** SQLite adapter compatible with better-sqlite3 and Node's synchronous SQLite API. */
export class SqliteAgentRegistryStore implements AgentRegistryStore {
  constructor(private readonly database: SqliteDatabase) {
    database.exec(`
      CREATE TABLE IF NOT EXISTS agentops_agents (
        agent_id TEXT NOT NULL,
        version TEXT NOT NULL,
        description TEXT NOT NULL,
        tools_json TEXT NOT NULL,
        PRIMARY KEY (agent_id, version)
      )
    `);
  }

  create(agent: AgentDefinition): boolean {
    const result = this.database.prepare(`
      INSERT OR IGNORE INTO agentops_agents
      (agent_id, version, description, tools_json) VALUES (?, ?, ?, ?)
    `).run(
      agent.agentId,
      agent.version,
      agent.description,
      JSON.stringify(agent.tools),
    );
    return result.changes === 1;
  }

  get(agentId: string, version: string): AgentDefinition | undefined {
    const row = this.database.prepare(`
      SELECT agent_id, version, description, tools_json
      FROM agentops_agents WHERE agent_id = ? AND version = ?
    `).get(agentId, version);
    return row === undefined ? undefined : this.fromRow(row);
  }

  list(agentId?: string): readonly AgentDefinition[] {
    const rows = agentId === undefined
      ? this.database.prepare(`
          SELECT agent_id, version, description, tools_json
          FROM agentops_agents ORDER BY agent_id COLLATE BINARY, version COLLATE BINARY
        `).all?.() 
      : undefined;
    if (agentId === undefined) {
      if (rows !== undefined) return rows.map((row) => this.fromRow(row));
      const result = this.database.prepare(`
        SELECT agent_id, version, description, tools_json
        FROM agentops_agents ORDER BY agent_id COLLATE BINARY, version COLLATE BINARY
      `);
      const all = (result as unknown as { all(): unknown[] }).all();
      return all.map((row) => this.fromRow(row));
    }
    const result = this.database.prepare(`
      SELECT agent_id, version, description, tools_json
      FROM agentops_agents WHERE agent_id = ?
      ORDER BY agent_id COLLATE BINARY, version COLLATE BINARY
    `);
    const statement = result as unknown as { all(...parameters: unknown[]): unknown[] };
    return statement.all(agentId).map((row) => this.fromRow(row));
  }

  private fromRow(value: unknown): AgentDefinition {
    if (typeof value !== "object" || value === null) {
      throw new TypeError("SQLite returned an invalid agent row");
    }
    const row = value as Record<string, unknown>;
    let tools: unknown;
    try {
      tools = JSON.parse(String(row.tools_json));
    } catch {
      throw new TypeError("Stored agent tools_json is invalid JSON");
    }
    if (!Array.isArray(tools) || tools.some((item) => typeof item !== "string")) {
      throw new TypeError("Stored agent tools_json must be a JSON array of strings");
    }
    return new AgentDefinition({
      agentId: String(row.agent_id),
      version: String(row.version),
      description: String(row.description),
      tools,
    });
  }
}

export interface AgentRegistryOptions {
  readonly store?: AgentRegistryStore;
}

/** Registry keyed by immutable (agentId, version) pairs. */
export class AgentRegistry {
  readonly store: AgentRegistryStore;

  constructor(options: AgentRegistryOptions = {}) {
    this.store = options.store ?? new InMemoryAgentRegistryStore();
  }

  register(agent: AgentDefinition): AgentDefinition {
    if (!(agent instanceof AgentDefinition)) {
      throw new TypeError("agent must be an AgentDefinition");
    }
    if (!this.store.create(agent)) {
      throw new AgentAlreadyRegisteredError(agent.agentId, agent.version);
    }
    return agent;
  }

  get(agentId: string, version: string): AgentDefinition {
    requireText(agentId, "agentId");
    requireText(version, "version");
    const agent = this.store.get(agentId, version);
    if (!agent) throw new AgentNotFoundError(agentId, version);
    return agent;
  }

  list(agentId?: string): readonly AgentDefinition[] {
    if (agentId !== undefined) requireText(agentId, "agentId");
    return this.store.list(agentId);
  }
}
