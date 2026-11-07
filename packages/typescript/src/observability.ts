export type ToolEventType = "tool.started" | "tool.succeeded" | "tool.failed";

export interface RunEvent {
  readonly type: ToolEventType;
  readonly runId: string;
  readonly toolName: string;
  readonly timestamp: string;
  readonly durationMs?: number;
  readonly errorType?: string;
}

export interface EventRecorder {
  record(event: RunEvent): void;
}

/** In-memory metadata recorder. Arguments, results, and secrets are not stored. */
export class InMemoryRecorder implements EventRecorder {
  private readonly recorded: RunEvent[] = [];

  record(event: RunEvent): void {
    this.recorded.push(Object.freeze({ ...event }));
  }

  get events(): readonly RunEvent[] {
    return this.recorded.slice();
  }

  clear(): void {
    this.recorded.length = 0;
  }
}
