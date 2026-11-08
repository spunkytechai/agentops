import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

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
