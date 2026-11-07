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

/** Process-local registry keyed by immutable (agentId, version) pairs. */
export class AgentRegistry {
  private readonly agents = new Map<string, AgentDefinition>();

  register(agent: AgentDefinition): AgentDefinition {
    if (!(agent instanceof AgentDefinition)) {
      throw new TypeError("agent must be an AgentDefinition");
    }
    const key = this.key(agent.agentId, agent.version);
    if (this.agents.has(key)) {
      throw new AgentAlreadyRegisteredError(agent.agentId, agent.version);
    }
    this.agents.set(key, agent);
    return agent;
  }

  get(agentId: string, version: string): AgentDefinition {
    const agent = this.agents.get(this.key(agentId, version));
    if (!agent) throw new AgentNotFoundError(agentId, version);
    return agent;
  }

  list(agentId?: string): readonly AgentDefinition[] {
    if (agentId !== undefined) requireText(agentId, "agentId");
    return [...this.agents.values()]
      .filter((agent) => agentId === undefined || agent.agentId === agentId)
      .sort((left, right) =>
        left.agentId.localeCompare(right.agentId) || left.version.localeCompare(right.version),
      );
  }

  private key(agentId: string, version: string): string {
    requireText(agentId, "agentId");
    requireText(version, "version");
    return JSON.stringify([agentId, version]);
  }
}
