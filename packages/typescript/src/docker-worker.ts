import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { WorkerProcess, type WorkerProcessOptions } from "./worker.js";

export interface DockerWorkerOptions extends WorkerProcessOptions {
  readonly dockerExecutable?: string;
  readonly memoryLimitBytes?: number;
  readonly cpuLimit?: number;
  readonly pidsLimit?: number;
  readonly tmpfsSizeBytes?: number;
}

function positiveSafeInteger(value: number, name: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) throw new TypeError(`${name} must be a positive safe integer`);
}

function removeContainer(dockerExecutable: string, name: string): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve();
    };
    let child;
    try {
      child = spawn(dockerExecutable, ["rm", "--force", name], {
        stdio: "ignore", windowsHide: true,
      });
    } catch {
      finish();
      return;
    }
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish();
    }, 5_000);
    child.once("error", finish);
    child.once("close", finish);
  });
}

/** Run the Phase 13 JSONL worker inside a hardened Docker container.
 * Docker daemon and host kernel remain trusted; this is not escape-proof isolation.
 */
export class DockerWorker {
  private readonly dockerExecutable: string;
  private readonly workerOptions: WorkerProcessOptions;
  private readonly memoryLimitBytes: number;
  private readonly cpuLimit: number;
  private readonly pidsLimit: number;
  private readonly tmpfsSizeBytes: number;

  constructor(
    private readonly image: string,
    options: DockerWorkerOptions = {},
  ) {
    if (!image || image.startsWith("-") || /\s/.test(image)) {
      throw new TypeError("image must be a non-empty Docker image reference without whitespace");
    }
    this.dockerExecutable = options.dockerExecutable ?? "docker";
    if (!this.dockerExecutable.trim()) throw new TypeError("dockerExecutable must be non-empty");
    this.memoryLimitBytes = options.memoryLimitBytes ?? 268_435_456;
    this.cpuLimit = options.cpuLimit ?? 1;
    this.pidsLimit = options.pidsLimit ?? 64;
    this.tmpfsSizeBytes = options.tmpfsSizeBytes ?? 16_777_216;
    positiveSafeInteger(this.memoryLimitBytes, "memoryLimitBytes");
    positiveSafeInteger(this.pidsLimit, "pidsLimit");
    positiveSafeInteger(this.tmpfsSizeBytes, "tmpfsSizeBytes");
    if (!Number.isFinite(this.cpuLimit) || this.cpuLimit <= 0) throw new TypeError("cpuLimit must be positive and finite");
    this.workerOptions = {
      ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
      ...(options.maxInputBytes !== undefined ? { maxInputBytes: options.maxInputBytes } : {}),
      ...(options.maxOutputBytes !== undefined ? { maxOutputBytes: options.maxOutputBytes } : {}),
    };
  }

  private runArgs(name: string): string[] {
    return [
      "run", "--rm", "--interactive", "--pull=never", `--name=${name}`,
      "--network=none", "--read-only", "--cap-drop=ALL",
      "--security-opt=no-new-privileges", "--user=65532:65532",
      `--memory=${this.memoryLimitBytes}`,
      `--memory-swap=${this.memoryLimitBytes}`,
      `--cpus=${this.cpuLimit}`, `--pids-limit=${this.pidsLimit}`,
      `--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=${this.tmpfsSizeBytes}`,
      this.image,
    ];
  }

  async execute(toolName: string, input: unknown, options: { readonly requestId?: string } = {}): Promise<unknown> {
    const name = `agentops-worker-${randomUUID()}`;
    const worker = new WorkerProcess(this.dockerExecutable, this.runArgs(name), this.workerOptions);
    try {
      return await worker.execute(toolName, input, options);
    } finally {
      await removeContainer(this.dockerExecutable, name);
    }
  }
}
