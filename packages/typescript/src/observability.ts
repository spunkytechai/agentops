export type ToolEventType = "tool.started" | "tool.succeeded" | "tool.failed";

export interface TraceContextOptions {
  readonly traceId: string;
  readonly spanId: string;
  readonly parentSpanId?: string;
}

/** W3C Trace Context identifiers; propagation is explicit and provider-neutral. */
export class TraceContext {
  readonly traceId: string;
  readonly spanId: string;
  readonly parentSpanId?: string;

  constructor(options: TraceContextOptions) {
    if (!/^[0-9a-f]{32}$/.test(options.traceId) || /^0+$/.test(options.traceId)) {
      throw new TypeError("traceId must be 32 lowercase hexadecimal characters and non-zero");
    }
    if (!/^[0-9a-f]{16}$/.test(options.spanId) || /^0+$/.test(options.spanId)) {
      throw new TypeError("spanId must be 16 lowercase hexadecimal characters and non-zero");
    }
    if (options.parentSpanId !== undefined &&
        (!/^[0-9a-f]{16}$/.test(options.parentSpanId) || /^0+$/.test(options.parentSpanId))) {
      throw new TypeError("parentSpanId must be 16 lowercase hexadecimal characters and non-zero");
    }
    if (options.parentSpanId === options.spanId) {
      throw new TypeError("parentSpanId must differ from spanId");
    }
    this.traceId = options.traceId;
    this.spanId = options.spanId;
    this.parentSpanId = options.parentSpanId;
    Object.freeze(this);
  }

  static create(parent?: TraceContext): TraceContext {
    const randomHex = (bytes: number) =>
      Array.from(globalThis.crypto.getRandomValues(new Uint8Array(bytes)))
        .map((value) => value.toString(16).padStart(2, "0")).join("");
    return new TraceContext({
      traceId: parent?.traceId ?? randomHex(16),
      spanId: randomHex(8),
      ...(parent === undefined ? {} : { parentSpanId: parent.spanId }),
    });
  }
}

export interface RunEvent {
  readonly type: ToolEventType;
  readonly runId: string;
  readonly toolName: string;
  readonly timestamp: string;
  readonly durationMs?: number;
  readonly errorType?: string;
  readonly traceId?: string;
  readonly spanId?: string;
  readonly parentSpanId?: string;
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
