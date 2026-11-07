import { InMemoryRecorder, TraceContext, type EventRecorder, type RunEvent } from "./observability.js";
import type { ApprovalManager } from "./approvals.js";
import { PolicyDeniedError, ToolPolicy } from "./policy.js";
import { canonicalActionJson, type ActionObject } from "./fingerprint.js";

export interface ToolExecutionOptions {
  readonly timeoutMs?: number;
  readonly principalId?: string;
  readonly traceContext?: TraceContext;
}

export interface ToolApprovalExecutionOptions extends ToolExecutionOptions {
  readonly principalId: string;
  readonly approvalManager: ApprovalManager;
  readonly approvalRequestId: string;
  readonly action: ActionObject;
}

export class ToolExecutionTimeoutError extends Error {
  readonly toolName: string;
  readonly timeoutMs: number;

  constructor(toolName: string, timeoutMs: number) {
    super(`Tool "${toolName}" exceeded ${timeoutMs} ms`);
    this.name = "ToolExecutionTimeoutError";
    this.toolName = toolName;
    this.timeoutMs = timeoutMs;
  }
}

/** Executes authorized tools and records lifecycle metadata, not payloads. */
export class ToolExecutor {
  private readonly recorder: EventRecorder;

  constructor(private readonly policy: ToolPolicy, recorder?: EventRecorder) {
    this.recorder = recorder ?? new InMemoryRecorder();
  }

  async execute<T>(
    toolName: string,
    operation: (signal: AbortSignal) => T | Promise<T>,
    runId: string = globalThis.crypto.randomUUID(),
    options: ToolExecutionOptions = {},
  ): Promise<T> {
    const timeoutMs = options.timeoutMs;
    if (timeoutMs !== undefined &&
        (typeof timeoutMs !== "number" || !Number.isFinite(timeoutMs) || timeoutMs <= 0)) {
      throw new TypeError("timeoutMs must be a positive finite number");
    }
    const decision = this.policy.evaluate(toolName, options.principalId);
    if (!decision.allowed) throw new PolicyDeniedError(toolName, decision.reason);

    const context = options.traceContext ?? TraceContext.create();
    this.recorder.record(this.event("tool.started", runId, toolName, undefined, undefined, context));
    const started = performance.now();
    const controller = new AbortController();
    let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
    try {
      const operationPromise = Promise.resolve().then(() => operation(controller.signal));
      let result: T;
      if (timeoutMs === undefined) {
        result = await operationPromise;
      } else {
        const timeoutPromise = new Promise<never>((_, reject) => {
          timeoutHandle = setTimeout(() => {
            reject(new ToolExecutionTimeoutError(toolName, timeoutMs));
            controller.abort();
          }, timeoutMs);
        });
        result = await Promise.race([operationPromise, timeoutPromise]);
      }
      this.recorder.record(this.event("tool.succeeded", runId, toolName, performance.now() - started, undefined, context));
      return result;
    } catch (error) {
      this.recorder.record(this.event(
        "tool.failed", runId, toolName, performance.now() - started,
        error instanceof Error ? error.name : "UnknownError", context,
      ));
      throw error;
    } finally {
      if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
    }
  }

  async executeApproved<T>(
    toolName: string,
    operation: (action: ActionObject, signal: AbortSignal) => T | Promise<T>,
    runId: string,
    options: ToolApprovalExecutionOptions,
  ): Promise<T> {
    const timeoutMs = options.timeoutMs;
    if (timeoutMs !== undefined &&
        (typeof timeoutMs !== "number" || !Number.isFinite(timeoutMs) || timeoutMs <= 0)) {
      throw new TypeError("timeoutMs must be a positive finite number");
    }
    const decision = this.policy.evaluate(toolName, options.principalId);
    if (!decision.allowed) throw new PolicyDeniedError(toolName, decision.reason);
    const approvedAction = JSON.parse(canonicalActionJson(options.action)) as ActionObject;
    options.approvalManager.consume(
      options.approvalRequestId, options.principalId, toolName, approvedAction,
    );
    return this.execute(
      toolName, (signal) => operation(approvedAction, signal), runId, options,
    );
  }

  private event(
    type: RunEvent["type"],
    runId: string,
    toolName: string,
    durationMs?: number,
    errorType?: string,
    traceContext?: TraceContext,
  ): RunEvent {
    return {
      type, runId, toolName, timestamp: new Date().toISOString(),
      ...(durationMs === undefined ? {} : { durationMs }),
      ...(errorType === undefined ? {} : { errorType }),
      ...(traceContext === undefined ? {} : {
        traceId: traceContext.traceId,
        spanId: traceContext.spanId,
        ...(traceContext.parentSpanId === undefined ? {} : { parentSpanId: traceContext.parentSpanId }),
      }),
    };
  }
}
