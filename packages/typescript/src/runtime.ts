import type { EventRecorder, RunEvent } from "./observability.js";
import { InMemoryRecorder } from "./observability.js";
import { PolicyDeniedError, ToolPolicy } from "./policy.js";

export interface ToolExecutionOptions {
  readonly timeoutMs?: number;
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
    runId = globalThis.crypto.randomUUID(),
    options: ToolExecutionOptions = {},
  ): Promise<T> {
    const timeoutMs = options.timeoutMs;
    if (timeoutMs !== undefined &&
        (typeof timeoutMs !== "number" || !Number.isFinite(timeoutMs) || timeoutMs <= 0)) {
      throw new TypeError("timeoutMs must be a positive finite number");
    }

    const decision = this.policy.evaluate(toolName);
    if (!decision.allowed) {
      throw new PolicyDeniedError(toolName, decision.reason);
    }

    this.recorder.record(this.event("tool.started", runId, toolName));
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
      this.recorder.record(this.event("tool.succeeded", runId, toolName, performance.now() - started));
      return result;
    } catch (error) {
      this.recorder.record(this.event(
        "tool.failed",
        runId,
        toolName,
        performance.now() - started,
        error instanceof Error ? error.name : "UnknownError",
      ));
      throw error;
    } finally {
      if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
    }
  }

  private event(
    type: RunEvent["type"],
    runId: string,
    toolName: string,
    durationMs?: number,
    errorType?: string,
  ): RunEvent {
    return {
      type,
      runId,
      toolName,
      timestamp: new Date().toISOString(),
      ...(durationMs === undefined ? {} : { durationMs }),
      ...(errorType === undefined ? {} : { errorType }),
    };
  }
}
