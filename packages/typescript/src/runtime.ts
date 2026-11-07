import type { EventRecorder, RunEvent } from "./observability.js";
import { InMemoryRecorder } from "./observability.js";
import { PolicyDeniedError, ToolPolicy } from "./policy.js";

/** Executes authorized tools and records lifecycle metadata, not payloads. */
export class ToolExecutor {
  private readonly recorder: EventRecorder;

  constructor(private readonly policy: ToolPolicy, recorder?: EventRecorder) {
    this.recorder = recorder ?? new InMemoryRecorder();
  }

  async execute<T>(
    toolName: string,
    operation: () => T | Promise<T>,
    runId = globalThis.crypto.randomUUID(),
  ): Promise<T> {
    const decision = this.policy.evaluate(toolName);
    if (!decision.allowed) {
      throw new PolicyDeniedError(toolName, decision.reason);
    }

    this.recorder.record(this.event("tool.started", runId, toolName));
    const started = performance.now();
    try {
      const result = await operation();
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
