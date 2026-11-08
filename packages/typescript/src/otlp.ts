import type { EventRecorder, RunEvent } from "./observability.js";

export type OtlpHttpTransport = (
  url: string,
  headers: Readonly<Record<string, string>>,
  body: string,
) => void | Promise<void>;

export interface OtlpHttpSpanExporterOptions {
  readonly maxQueueSize?: number;
  readonly maxBatchSize?: number;
  readonly maxRetries?: number;
}

type OtlpAttributeValue = string | number | boolean;
type OtlpSpan = {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  kind: number;
  startTimeUnixNano: string;
  endTimeUnixNano: string;
  attributes: { key: string; value: Record<string, OtlpAttributeValue> }[];
  status: { code: number };
};

/** Dependency-free OTLP/HTTP JSON exporter; HTTP transport is injected by the host. */
export class OtlpHttpSpanExporter implements EventRecorder {
  private readonly endpoint: string;
  private readonly transport: OtlpHttpTransport;
  private readonly maxQueueSize: number;
  private readonly maxBatchSize: number;
  private readonly maxRetries: number;
  private readonly pending = new Map<string, RunEvent>();
  private readonly queue: OtlpSpan[] = [];
  droppedSpans = 0;

  constructor(endpoint: string, transport: OtlpHttpTransport, options: OtlpHttpSpanExporterOptions = {}) {
    let parsed: URL;
    try {
      parsed = new URL(endpoint);
    } catch {
      throw new TypeError("endpoint must be an absolute HTTP or HTTPS URL");
    }
    if ((parsed.protocol !== "http:" && parsed.protocol !== "https:") || parsed.search || parsed.hash) {
      throw new TypeError("endpoint must be an absolute HTTP or HTTPS URL");
    }
    const maxQueueSize = options.maxQueueSize ?? 2048;
    const maxBatchSize = options.maxBatchSize ?? 512;
    const maxRetries = options.maxRetries ?? 2;
    if (!Number.isSafeInteger(maxQueueSize) || maxQueueSize <= 0 ||
        !Number.isSafeInteger(maxBatchSize) || maxBatchSize <= 0) {
      throw new TypeError("queue and batch sizes must be positive integers");
    }
    if (!Number.isSafeInteger(maxRetries) || maxRetries < 0) {
      throw new TypeError("maxRetries must be a non-negative integer");
    }
    this.endpoint = endpoint.replace(/\/+$/, "") + "/v1/traces";
    this.transport = transport;
    this.maxQueueSize = maxQueueSize;
    this.maxBatchSize = Math.min(maxBatchSize, maxQueueSize);
    this.maxRetries = maxRetries;
  }

  record(event: RunEvent): void {
    if (event.traceId === undefined || event.spanId === undefined) return;
    const key = this.key(event.traceId, event.spanId);
    if (event.type === "tool.started") {
      if (this.pending.size + this.queue.length >= this.maxQueueSize) {
        this.droppedSpans += 1;
        return;
      }
      this.pending.set(key, Object.freeze({ ...event }));
      return;
    }
    const started = this.pending.get(key);
    if (started === undefined) return;
    this.pending.delete(key);
    if (this.queue.length >= this.maxQueueSize) {
      this.droppedSpans += 1;
      return;
    }
    this.queue.push(this.toSpan(started, event));
  }

  async flush(): Promise<number> {
    let exported = 0;
    while (this.queue.length > 0) {
      const batch = this.queue.splice(0, this.maxBatchSize);
      const body = JSON.stringify({
        resourceSpans: [{
          resource: { attributes: [] },
          scopeSpans: [{
            scope: { name: "agentops", version: "0.1.0" },
            spans: batch,
          }],
        }],
      });
      let failure: unknown;
      let succeeded = false;
      for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
        try {
          await this.transport(this.endpoint, { "Content-Type": "application/json" }, body);
          succeeded = true;
          break;
        } catch (error) {
          failure = error;
        }
      }
      if (!succeeded) {
        this.queue.unshift(...batch);
        throw failure;
      }
      exported += batch.length;
    }
    return exported;
  }

  private key(traceId: string, spanId: string): string {
    return `${traceId}\u0000${spanId}`;
  }

  private toSpan(started: RunEvent, ended: RunEvent): OtlpSpan {
    const success = ended.type === "tool.succeeded";
    const attributes: OtlpSpan["attributes"] = [
      this.attribute("agentops.run_id", started.runId),
      this.attribute("agentops.tool_name", started.toolName),
      this.attribute("agentops.status", success ? "ok" : "error"),
    ];
    if (ended.durationMs !== undefined) {
      attributes.push(this.attribute("agentops.duration_ms", ended.durationMs));
    }
    if (ended.errorType !== undefined) {
      attributes.push(this.attribute("error.type", ended.errorType));
    }
    return {
      traceId: started.traceId!,
      spanId: started.spanId!,
      ...(started.parentSpanId === undefined ? {} : { parentSpanId: started.parentSpanId }),
      name: started.toolName,
      kind: 1,
      startTimeUnixNano: this.toUnixNano(started.timestamp),
      endTimeUnixNano: this.toUnixNano(ended.timestamp),
      attributes,
      status: { code: success ? 1 : 2 },
    };
  }

  private attribute(key: string, value: OtlpAttributeValue): OtlpSpan["attributes"][number] {
    const field = typeof value === "boolean" ? "boolValue"
      : typeof value === "number" ? "doubleValue" : "stringValue";
    return { key, value: { [field]: value } };
  }

  private toUnixNano(timestamp: string): string {
    const milliseconds = Date.parse(timestamp);
    if (!Number.isFinite(milliseconds)) throw new TypeError("event timestamp must be a valid ISO date");
    return (BigInt(milliseconds) * 1_000_000n).toString();
  }
}
