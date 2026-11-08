import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

function assertWellFormedUnicode(value: string, path: string): void {
  for (let index = 0; index < value.length; index++) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new TypeError(`${path} contains an unpaired Unicode surrogate`);
      }
      index++;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new TypeError(`${path} contains an unpaired Unicode surrogate`);
    }
  }
}

function assertJsonValue(value: unknown, path: string, ancestors = new Set<object>()): void {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    assertWellFormedUnicode(value, path);
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError(`${path} must be a finite JSON number`);
    return;
  }
  if (typeof value !== "object") {
    throw new TypeError(`${path} contains a value that is not JSON-compatible`);
  }
  if (ancestors.has(value)) throw new TypeError(`${path} contains a circular reference`);
  ancestors.add(value);
  try {
    if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index++) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
        if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) {
          throw new TypeError(`${path} must not contain sparse arrays or accessor elements`);
        }
        assertJsonValue(descriptor.value, `${path}[${index}]`, ancestors);
      }
      for (const key of Reflect.ownKeys(value)) {
        if (typeof key === "symbol" || (key !== "length" && !/^(0|[1-9]\\d*)$/.test(key))) {
          throw new TypeError(`${path} contains an unsupported array property`);
        }
      }
      return;
    }
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new TypeError(`${path} must contain only plain JSON objects`);
    }
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== "string") throw new TypeError(`${path} contains a symbol key`);
      assertWellFormedUnicode(key, `${path} object key`);
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined || !descriptor.enumerable || !("value" in descriptor)) {
        throw new TypeError(`${path} contains a non-JSON property`);
      }
      assertJsonValue(descriptor.value, `${path}.${key}`, ancestors);
    }
  } finally {
    ancestors.delete(value);
  }
}

export class WorkerExecutionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkerExecutionError";
  }
}

export interface WorkerProcessOptions {
  readonly timeoutMs?: number;
  readonly maxInputBytes?: number;
  readonly maxOutputBytes?: number;
}

export interface WorkerRequestOptions {
  readonly requestId?: string;
}

/** Executes one versioned JSONL request in a fresh child process.
 * A child process is not an OS/container sandbox; the host must apply isolation.
 */
export class WorkerProcess {
  private readonly timeoutMs: number;
  private readonly maxInputBytes: number;
  private readonly maxOutputBytes: number;

  constructor(
    private readonly executable: string,
    private readonly args: readonly string[] = [],
    options: WorkerProcessOptions = {},
  ) {
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.maxInputBytes = options.maxInputBytes ?? 1_048_576;
    this.maxOutputBytes = options.maxOutputBytes ?? 1_048_576;
    if (!executable.trim()) throw new TypeError("executable must be non-empty");
    if (!Number.isFinite(this.timeoutMs) || this.timeoutMs <= 0) throw new TypeError("timeoutMs must be positive and finite");
    for (const limit of [this.maxInputBytes, this.maxOutputBytes]) {
      if (!Number.isSafeInteger(limit) || limit <= 0) throw new TypeError("byte limits must be positive safe integers");
    }
  }

  execute(toolName: string, input: unknown, options: WorkerRequestOptions = {}): Promise<unknown> {
    if (!toolName.trim()) return Promise.reject(new TypeError("toolName must be non-empty"));
    const requestId = options.requestId ?? randomUUID();
    if (!requestId.trim()) return Promise.reject(new TypeError("requestId must be non-empty"));
    let request: Buffer;
    try {
      assertJsonValue(input, "input");
      request = Buffer.from(JSON.stringify({
        protocol_version: 1, request_id: requestId, tool_name: toolName, input,
      }) + "\n", "utf8");
    } catch {
      return Promise.reject(new WorkerExecutionError("worker request is not valid JSON"));
    }
    if (request.length > this.maxInputBytes) {
      return Promise.reject(new WorkerExecutionError("worker input byte limit exceeded"));
    }

    return new Promise((resolve, reject) => {
      const child = spawn(this.executable, [...this.args], {
        stdio: ["pipe", "pipe", "ignore"],
        windowsHide: true,
      });
      const chunks: Buffer[] = [];
      let outputBytes = 0;
      let settled = false;
      const finishError = (error: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        child.kill("SIGKILL");
        reject(error);
      };
      const timer = setTimeout(() => finishError(new WorkerExecutionError("worker execution deadline exceeded")), this.timeoutMs);
      child.once("error", () => finishError(new WorkerExecutionError("worker could not be started")));
      child.stdout.on("data", (chunk: Buffer) => {
        if (settled) return;
        outputBytes += chunk.length;
        if (outputBytes > this.maxOutputBytes) {
          finishError(new WorkerExecutionError("worker output byte limit exceeded"));
          return;
        }
        chunks.push(Buffer.from(chunk));
      });
      child.once("close", (code) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (code !== 0) {
          reject(new WorkerExecutionError("worker exited unsuccessfully"));
          return;
        }
        const output = Buffer.concat(chunks);
        if (!output.length || output[output.length - 1] !== 10 || output.subarray(0, -1).includes(10)) {
          reject(new WorkerExecutionError("worker must return exactly one JSONL response"));
          return;
        }
        let response: unknown;
        try { response = JSON.parse(output.subarray(0, -1).toString("utf8")); }
        catch { reject(new WorkerExecutionError("worker returned invalid JSON")); return; }
        if (typeof response !== "object" || response === null ||
            (response as Record<string, unknown>).protocol_version !== 1 ||
            (response as Record<string, unknown>).request_id !== requestId ||
            !Object.hasOwn(response, "result")) {
          reject(new WorkerExecutionError("worker response does not match the request protocol"));
          return;
        }
        resolve((response as Record<string, unknown>).result);
      });
      child.stdin.on("error", () => finishError(new WorkerExecutionError("worker communication failed")));
      child.stdin.end(request);
    });
  }
}
