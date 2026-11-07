export interface PolicyRuleOptions {
  readonly principalId: string;
  readonly toolName: string;
  readonly effect: "allow" | "deny";
}

export class PolicyRule {
  readonly principalId: string;
  readonly toolName: string;
  readonly effect: "allow" | "deny";

  constructor(options: PolicyRuleOptions) {
    if (typeof options.principalId !== "string" || options.principalId.trim().length === 0) {
      throw new TypeError("principalId must be a non-empty string");
    }
    if (typeof options.toolName !== "string" || options.toolName.trim().length === 0) {
      throw new TypeError("toolName must be a non-empty string");
    }
    if (options.effect !== "allow" && options.effect !== "deny") {
      throw new TypeError("effect must be 'allow' or 'deny'");
    }
    this.principalId = options.principalId;
    this.toolName = options.toolName;
    this.effect = options.effect;
    Object.freeze(this);
  }
}

export interface ToolPolicyOptions {
  readonly allowedTools?: readonly string[];
  readonly deniedTools?: readonly string[];
  readonly rules?: readonly PolicyRule[];
}

export interface PolicyDecision {
  readonly allowed: boolean;
  readonly toolName: string;
  readonly reason:
    | "explicitly allowed"
    | "explicitly denied"
    | "principal-scoped allow rule"
    | "principal-scoped deny rule"
    | "not present in allow-list";
}

/** Deny-by-default policy. Explicit global and scoped denies take precedence. */
export class ToolPolicy {
  private readonly allowedTools: ReadonlySet<string>;
  private readonly deniedTools: ReadonlySet<string>;
  private readonly rules: readonly PolicyRule[];

  constructor(options: ToolPolicyOptions = {}) {
    const allowed = options.allowedTools ?? [];
    const denied = options.deniedTools ?? [];
    for (const name of [...allowed, ...denied]) {
      if (typeof name !== "string" || name.trim().length === 0) {
        throw new TypeError("Tool names must be non-empty strings");
      }
    }
    const rules = [...(options.rules ?? [])];
    if (rules.some((rule) => !(rule instanceof PolicyRule))) {
      throw new TypeError("rules must contain PolicyRule instances");
    }
    this.allowedTools = new Set(allowed);
    this.deniedTools = new Set(denied);
    this.rules = Object.freeze(rules);
  }

  evaluate(toolName: string, principalId?: string): PolicyDecision {
    if (typeof toolName !== "string" || toolName.trim().length === 0) {
      throw new TypeError("toolName must be a non-empty string");
    }
    if (principalId !== undefined &&
        (typeof principalId !== "string" || principalId.trim().length === 0)) {
      throw new TypeError("principalId must be a non-empty string when provided");
    }

    const scopedEffects = principalId === undefined
      ? []
      : this.rules
        .filter((rule) => rule.toolName === toolName && rule.principalId === principalId)
        .map((rule) => rule.effect);

    if (this.deniedTools.has(toolName) || scopedEffects.includes("deny")) {
      return {
        allowed: false,
        toolName,
        reason: this.deniedTools.has(toolName) ? "explicitly denied" : "principal-scoped deny rule",
      };
    }
    if (this.allowedTools.has(toolName)) {
      return { allowed: true, toolName, reason: "explicitly allowed" };
    }
    if (scopedEffects.includes("allow")) {
      return { allowed: true, toolName, reason: "principal-scoped allow rule" };
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
