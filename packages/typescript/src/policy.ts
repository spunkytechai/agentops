export interface ToolPolicyOptions {
  readonly allowedTools?: readonly string[];
  readonly deniedTools?: readonly string[];
}

export interface PolicyDecision {
  readonly allowed: boolean;
  readonly toolName: string;
  readonly reason: "explicitly allowed" | "explicitly denied" | "not present in allow-list";
}

/** Deny-by-default policy. Explicit deny rules always take precedence. */
export class ToolPolicy {
  private readonly allowedTools: ReadonlySet<string>;
  private readonly deniedTools: ReadonlySet<string>;

  constructor(options: ToolPolicyOptions = {}) {
    const allowed = options.allowedTools ?? [];
    const denied = options.deniedTools ?? [];
    for (const name of [...allowed, ...denied]) {
      if (typeof name !== "string" || name.trim().length === 0) {
        throw new TypeError("Tool names must be non-empty strings");
      }
    }
    this.allowedTools = new Set(allowed);
    this.deniedTools = new Set(denied);
  }

  evaluate(toolName: string): PolicyDecision {
    if (typeof toolName !== "string" || toolName.trim().length === 0) {
      throw new TypeError("toolName must be a non-empty string");
    }
    if (this.deniedTools.has(toolName)) {
      return { allowed: false, toolName, reason: "explicitly denied" };
    }
    if (this.allowedTools.has(toolName)) {
      return { allowed: true, toolName, reason: "explicitly allowed" };
    }
    return { allowed: false, toolName, reason: "not present in allow-list" };
  }
}

export class PolicyDeniedError extends Error {
  readonly toolName: string;
  readonly reason: string;

  constructor(toolName: string, reason: string) {
    super(`Tool "${toolName}" denied: ${reason}`);
    this.name = "PolicyDeniedError";
    this.toolName = toolName;
    this.reason = reason;
  }
}
