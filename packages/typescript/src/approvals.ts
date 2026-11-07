import { actionFingerprint, type ActionObject } from "./fingerprint.js";

export type ApprovalStatus = "pending" | "approved" | "denied" | "consumed" | "expired";

export interface ApprovalRequestOptions {
  readonly principalId: string;
  readonly toolName: string;
  readonly summary: string;
  readonly ttlSeconds?: number;
  readonly action?: ActionObject;
}

export interface ApprovalRequest {
  readonly requestId: string;
  readonly principalId: string;
  readonly toolName: string;
  readonly summary: string;
  readonly status: ApprovalStatus;
  readonly expiresAt: number;
  readonly approverId?: string;
  readonly reason?: string;
  readonly actionFingerprint?: string;
}

export interface ApprovalGrant {
  readonly requestId: string;
  readonly principalId: string;
  readonly toolName: string;
  readonly approverId: string;
  readonly actionFingerprint?: string;
}

export interface SqliteRunResult { readonly changes: number }
export interface SqliteStatement {
  run(...parameters: unknown[]): SqliteRunResult;
  get(...parameters: unknown[]): unknown;
}
export interface SqliteDatabase {
  exec(sql: string): void;
  prepare(sql: string): SqliteStatement;
}

/** Store implementations must make consume a single atomic compare-and-consume operation. */
export interface ApprovalStore {
  create(request: ApprovalRequest): void;
  get(requestId: string): ApprovalRequest | undefined;
  transition(requestId: string, expectedStatus: ApprovalStatus, updated: ApprovalRequest): boolean;
  consume(
    requestId: string, principalId: string, toolName: string,
    actionFingerprint: string | undefined, now: number,
  ): ApprovalRequest | undefined;
}

export interface ApprovalManagerOptions {
  readonly clock?: () => number;
  readonly store?: ApprovalStore;
}

export class ApprovalRequiredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApprovalRequiredError";
  }
}

export class ApprovalDeniedError extends ApprovalRequiredError {
  constructor(message: string) {
    super(message);
    this.name = "ApprovalDeniedError";
  }
}

export class InMemoryApprovalStore implements ApprovalStore {
  private readonly records = new Map<string, ApprovalRequest>();

  create(request: ApprovalRequest): void {
    if (this.records.has(request.requestId)) throw new TypeError("approval request already exists");
    this.records.set(request.requestId, request);
  }

  get(requestId: string): ApprovalRequest | undefined {
    return this.records.get(requestId);
  }

  transition(requestId: string, expectedStatus: ApprovalStatus, updated: ApprovalRequest): boolean {
    const current = this.records.get(requestId);
    if (current === undefined || current.status !== expectedStatus) return false;
    this.records.set(requestId, updated);
    return true;
  }

  consume(
    requestId: string, principalId: string, toolName: string,
    fingerprint: string | undefined, now: number,
  ): ApprovalRequest | undefined {
    const current = this.records.get(requestId);
    if (
      current === undefined || current.status !== "approved" ||
      current.principalId !== principalId || current.toolName !== toolName ||
      current.actionFingerprint !== fingerprint || current.approverId === undefined ||
      current.expiresAt <= now
    ) return undefined;
    const consumed = Object.freeze({ ...current, status: "consumed" as const });
    this.records.set(requestId, consumed);
    return consumed;
  }
}

/** SQLite adapter compatible with better-sqlite3 and Node's synchronous SQLite API. */
export class SqliteApprovalStore implements ApprovalStore {
  constructor(private readonly database: SqliteDatabase) {
    database.exec(`
      CREATE TABLE IF NOT EXISTS agentops_approvals (
        request_id TEXT PRIMARY KEY,
        principal_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        summary TEXT NOT NULL,
        status TEXT NOT NULL,
        expires_at_ms REAL NOT NULL,
        approver_id TEXT,
        reason TEXT,
        action_fingerprint TEXT
      )
    `);
    database.exec(
      "CREATE INDEX IF NOT EXISTS idx_agentops_approvals_status ON agentops_approvals(status, expires_at_ms)",
    );
  }

  create(request: ApprovalRequest): void {
    this.database.prepare(`
      INSERT INTO agentops_approvals
      (request_id, principal_id, tool_name, summary, status, expires_at_ms,
       approver_id, reason, action_fingerprint)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      request.requestId, request.principalId, request.toolName, request.summary,
      request.status, request.expiresAt, request.approverId ?? null,
      request.reason ?? null, request.actionFingerprint ?? null,
    );
  }

  get(requestId: string): ApprovalRequest | undefined {
    const row = this.database.prepare(
      "SELECT * FROM agentops_approvals WHERE request_id = ?",
    ).get(requestId);
    return row === undefined ? undefined : this.fromRow(row);
  }

  transition(requestId: string, expectedStatus: ApprovalStatus, updated: ApprovalRequest): boolean {
    const result = this.database.prepare(`
      UPDATE agentops_approvals SET status = ?, approver_id = ?, reason = ?
      WHERE request_id = ? AND status = ?
    `).run(
      updated.status, updated.approverId ?? null, updated.reason ?? null,
      requestId, expectedStatus,
    );
    return result.changes === 1;
  }

  consume(
    requestId: string, principalId: string, toolName: string,
    fingerprint: string | undefined, now: number,
  ): ApprovalRequest | undefined {
    const result = this.database.prepare(`
      UPDATE agentops_approvals SET status = 'consumed'
      WHERE request_id = ? AND principal_id = ? AND tool_name = ?
        AND status = 'approved' AND approver_id IS NOT NULL
        AND expires_at_ms > ? AND action_fingerprint IS ?
    `).run(requestId, principalId, toolName, now, fingerprint ?? null);
    return result.changes === 1 ? this.get(requestId) : undefined;
  }

  private fromRow(value: unknown): ApprovalRequest {
    if (typeof value !== "object" || value === null) {
      throw new TypeError("SQLite returned an invalid approval row");
    }
    const row = value as Record<string, unknown>;
    return Object.freeze({
      requestId: String(row.request_id),
      principalId: String(row.principal_id),
      toolName: String(row.tool_name),
      summary: String(row.summary),
      status: String(row.status) as ApprovalStatus,
      expiresAt: Number(row.expires_at),
      ...(row.approver_id === null ? {} : { approverId: String(row.approver_id) }),
      ...(row.reason === null ? {} : { reason: String(row.reason) }),
      ...(row.action_fingerprint === null ? {} : { actionFingerprint: String(row.action_fingerprint) }),
    });
  }
}

/** Approval state machine. Host applications authenticate and authorize approvers. */
export class ApprovalManager {
  private readonly clock: () => number;
  readonly store: ApprovalStore;

  constructor(options: ApprovalManagerOptions = {}) {
    this.clock = options.clock ?? Date.now;
    this.store = options.store ?? new InMemoryApprovalStore();
  }

  request(options: ApprovalRequestOptions): ApprovalRequest {
    this.validateIdentity(options.principalId, "principalId");
    this.validateIdentity(options.toolName, "toolName");
    this.validateIdentity(options.summary, "summary");
    const ttlSeconds = options.ttlSeconds ?? 300;
    if (typeof ttlSeconds !== "number" || !Number.isFinite(ttlSeconds) || ttlSeconds <= 0) {
      throw new RangeError("ttlSeconds must be a positive finite number");
    }
    const request: ApprovalRequest = Object.freeze({
      requestId: globalThis.crypto.randomUUID(),
      principalId: options.principalId,
      toolName: options.toolName,
      summary: options.summary,
      status: "pending",
      expiresAt: this.clock() + ttlSeconds * 1000,
      ...(options.action === undefined ? {} : { actionFingerprint: actionFingerprint(options.action) }),
    });
    this.store.create(request);
    return request;
  }

  get(requestId: string): ApprovalRequest {
    return this.expireIfNeeded(this.getRecord(requestId));
  }

  approve(requestId: string, approverId: string): ApprovalRequest {
    this.validateIdentity(approverId, "approverId");
    const request = this.get(requestId);
    if (request.status !== "pending") {
      throw new ApprovalDeniedError(`Approval request "${requestId}" is ${request.status}`);
    }
    const updated = this.replace(request, { status: "approved", approverId });
    if (!this.store.transition(requestId, "pending", updated)) {
      throw new ApprovalDeniedError(`Approval request "${requestId}" is ${this.get(requestId).status}`);
    }
    return updated;
  }

  deny(requestId: string, approverId: string, reason: string): ApprovalRequest {
    this.validateIdentity(approverId, "approverId");
    this.validateIdentity(reason, "reason");
    const request = this.get(requestId);
    if (request.status !== "pending") {
      throw new ApprovalDeniedError(`Approval request "${requestId}" is ${request.status}`);
    }
    const updated = this.replace(request, { status: "denied", approverId, reason });
    if (!this.store.transition(requestId, "pending", updated)) {
      throw new ApprovalDeniedError(`Approval request "${requestId}" is ${this.get(requestId).status}`);
    }
    return updated;
  }

  consume(
    requestId: string,
    principalId: string,
    toolName: string,
    action?: ActionObject,
  ): ApprovalGrant {
    const request = this.get(requestId);
    if (request.principalId !== principalId || request.toolName !== toolName) {
      throw new ApprovalRequiredError("Approval does not match this principal and tool");
    }
    if (request.status === "denied") {
      throw new ApprovalDeniedError(`Approval request "${requestId}" was denied`);
    }
    if (request.status !== "approved" || request.approverId === undefined) {
      throw new ApprovalRequiredError(`Approval request "${requestId}" is ${request.status}`);
    }
    const fingerprint = action === undefined ? undefined : actionFingerprint(action);
    if (fingerprint !== request.actionFingerprint) {
      throw new ApprovalRequiredError("Approval does not match the canonical action");
    }
    const consumed = this.store.consume(
      requestId, principalId, toolName, fingerprint, this.clock(),
    );
    if (consumed === undefined) {
      const latest = this.get(requestId);
      if (latest.status === "denied") {
        throw new ApprovalDeniedError(`Approval request "${requestId}" was denied`);
      }
      throw new ApprovalRequiredError(`Approval request "${requestId}" is ${latest.status}`);
    }
    return Object.freeze({
      requestId: consumed.requestId,
      principalId: consumed.principalId,
      toolName: consumed.toolName,
      approverId: consumed.approverId ?? "",
      ...(consumed.actionFingerprint === undefined ? {} : { actionFingerprint: consumed.actionFingerprint }),
    });
  }

  private getRecord(requestId: string): ApprovalRequest {
    const request = this.store.get(requestId);
    if (request === undefined) {
      throw new ApprovalRequiredError(`Unknown approval request "${requestId}"`);
    }
    return request;
  }

  private expireIfNeeded(request: ApprovalRequest): ApprovalRequest {
    if ((request.status === "pending" || request.status === "approved") &&
        this.clock() >= request.expiresAt) {
      const expired = this.replace(request, { status: "expired" });
      if (this.store.transition(request.requestId, request.status, expired)) return expired;
      return this.getRecord(request.requestId);
    }
    return request;
  }

  private replace(
    request: ApprovalRequest,
    changes: Partial<Pick<ApprovalRequest, "status" | "approverId" | "reason">>,
  ): ApprovalRequest {
    return Object.freeze({ ...request, ...changes });
  }

  private validateIdentity(value: string, name: string): void {
    if (typeof value !== "string" || value.trim().length === 0) {
      throw new TypeError(`${name} must be a non-empty string`);
    }
  }
}
