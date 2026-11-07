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

export interface ApprovalManagerOptions {
  readonly clock?: () => number;
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

/** Process-local approval state machine. Host applications authenticate approvers. */
export class ApprovalManager {
  private readonly records = new Map<string, ApprovalRequest>();
  private readonly clock: () => number;

  constructor(options: ApprovalManagerOptions = {}) {
    this.clock = options.clock ?? Date.now;
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
    this.records.set(request.requestId, request);
    return request;
  }

  get(requestId: string): ApprovalRequest {
    return this.expireIfNeeded(this.getRecord(requestId));
  }

  approve(requestId: string, approverId: string): ApprovalRequest {
    this.validateIdentity(approverId, "approverId");
    const request = this.expireIfNeeded(this.getRecord(requestId));
    if (request.status !== "pending") {
      throw new ApprovalDeniedError(`Approval request "${requestId}" is ${request.status}`);
    }
    return this.replace(requestId, { status: "approved", approverId });
  }

  deny(requestId: string, approverId: string, reason: string): ApprovalRequest {
    this.validateIdentity(approverId, "approverId");
    this.validateIdentity(reason, "reason");
    const request = this.expireIfNeeded(this.getRecord(requestId));
    if (request.status !== "pending") {
      throw new ApprovalDeniedError(`Approval request "${requestId}" is ${request.status}`);
    }
    return this.replace(requestId, { status: "denied", approverId, reason });
  }

  consume(
    requestId: string,
    principalId: string,
    toolName: string,
    action?: ActionObject,
  ): ApprovalGrant {
    const request = this.expireIfNeeded(this.getRecord(requestId));
    if (request.principalId !== principalId || request.toolName !== toolName) {
      throw new ApprovalRequiredError("Approval does not match this principal and tool");
    }
    if (request.status === "denied") {
      throw new ApprovalDeniedError(`Approval request "${requestId}" was denied`);
    }
    if (request.status !== "approved" || request.approverId === undefined) {
      throw new ApprovalRequiredError(`Approval request "${requestId}" is ${request.status}`);
    }
    const suppliedFingerprint = action === undefined ? undefined : actionFingerprint(action);
    if (suppliedFingerprint !== request.actionFingerprint) {
      throw new ApprovalRequiredError("Approval does not match the canonical action");
    }
    this.replace(requestId, { status: "consumed" });
    return Object.freeze({
      requestId: request.requestId,
      principalId: request.principalId,
      toolName: request.toolName,
      approverId: request.approverId,
      ...(request.actionFingerprint === undefined ? {} : { actionFingerprint: request.actionFingerprint }),
    });
  }

  private getRecord(requestId: string): ApprovalRequest {
    const request = this.records.get(requestId);
    if (request === undefined) {
      throw new ApprovalRequiredError(`Unknown approval request "${requestId}"`);
    }
    return request;
  }

  private expireIfNeeded(request: ApprovalRequest): ApprovalRequest {
    if ((request.status === "pending" || request.status === "approved") &&
        this.clock() >= request.expiresAt) {
      return this.replace(request.requestId, { status: "expired" });
    }
    return request;
  }

  private replace(
    requestId: string,
    changes: Partial<Pick<ApprovalRequest, "status" | "approverId" | "reason">>,
  ): ApprovalRequest {
    const updated = Object.freeze({ ...this.getRecord(requestId), ...changes });
    this.records.set(requestId, updated);
    return updated;
  }

  private validateIdentity(value: string, name: string): void {
    if (typeof value !== "string" || value.trim().length === 0) {
      throw new TypeError(`${name} must be a non-empty string`);
    }
  }
}
