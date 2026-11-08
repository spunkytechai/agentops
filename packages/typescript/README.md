# AgentOps TypeScript SDK

The TypeScript SDK provides deny-by-default tool authorization, versioned agent registration, metadata-only execution recording, and durable approval and registry storage.

## Development
```bash
npm install
npm test
```

## Durable approval storage
The SQLite adapter accepts a synchronous database handle compatible with `better-sqlite3`:

```ts
import Database from "better-sqlite3";
import { ApprovalManager, SqliteApprovalStore } from "@spunkytech/agentops";

const database = new Database("agentops.sqlite3");
const approvals = new ApprovalManager({ store: new SqliteApprovalStore(database) });
```

The application owns the connection lifecycle. For multi-host deployments, implement `ApprovalStore` using a transactional database with atomic compare-and-consume semantics.

## Durable agent registry

```ts
import Database from "better-sqlite3";
import { AgentDefinition, AgentRegistry, SqliteAgentRegistryStore } from "@spunkytech/agentops";

const database = new Database("agentops.sqlite3");
const registry = new AgentRegistry({ store: new SqliteAgentRegistryStore(database) });
registry.register(new AgentDefinition({
  agentId: "support.assistant",
  version: "1.0.0",
  description: "Customer support agent",
  tools: ["knowledge.search", "ticket.create"],
}));
```

Both SDKs use the same `agentops_agents` SQLite schema. A composite primary key prevents duplicate versions across connections. The application owns the database connection lifecycle. For multi-host deployments, implement `AgentRegistryStore` using a transactional database.

## Trace correlation

```ts
import { TraceContext } from "@spunkytech/agentops";

const parent = TraceContext.create();
const child = TraceContext.create(parent);
await executor.execute("reports.read", fetchReport, "report-run-1", {
  traceContext: child,
});
```

When omitted, the executor creates trace and span identifiers. Export completed tool spans using an injected asynchronous HTTP transport:


```ts
import { OtlpHttpSpanExporter, ToolExecutor } from "@spunkytech/agentops";

const exporter = new OtlpHttpSpanExporter("http://localhost:4318", async (url, headers, body) => {
  const response = await fetch(url, { method: "POST", headers, body });
  if (!response.ok) throw new Error("OTLP collector returned " + response.status);
}, { maxAttributeBytes: 256 });
const executor = new ToolExecutor(policy, exporter);
// Await exporter.flush() from a worker or controlled shutdown hook.
```

## Example
```ts
import { InMemoryRecorder, ToolExecutor, ToolPolicy } from "@spunkytech/agentops";

const recorder = new InMemoryRecorder();
const executor = new ToolExecutor(
  new ToolPolicy({ allowedTools: ["weather.lookup"] }),
  recorder,
);

const result = await executor.execute(
  "weather.lookup",
  async (signal) => {
    const response = await fetch("https://api.example.test/weather", { signal });
    if (!response.ok) throw new Error("Weather service failed");
    return response.json();
  },
  "weather-run-1",
  { timeoutMs: 5000 },
);

console.log(result, recorder.events.map((event) => event.type));
```

The operation receives an `AbortSignal`. Propagate it to cancellable APIs; otherwise, timed-out work may continue in the background. The default recorder excludes arguments, results, prompts, and credentials.

## Evaluation

```ts
import { EvaluationCase, EvaluationSuite, ExactMatchMetric, compareEvaluations } from "@spunkytech/agentops";

const suite = new EvaluationSuite("answer-quality", [
  new EvaluationCase("greeting", { prompt: "hello" }, "Hello!", { weight: 2 }),
], { metric: new ExactMatchMetric() });
const report = await suite.run(async (item) => "Hello!");
console.log(report.weightedScore, report.passRate);
// Compare a later report with a stored baseline:
// const regression = compareEvaluations(baseline, report, 0.02);
```

Use `NumericToleranceMetric(0.5)` for numeric outputs. Evaluation cases run sequentially; dataset storage, model-provider calls, and baseline persistence remain host responsibilities.

## Persist evaluation runs and baselines

```ts
import Database from "better-sqlite3";
import { SqliteEvaluationRunStore } from "@spunkytech/agentops";

const database = new Database("agentops-evaluations.sqlite3");
const store = new SqliteEvaluationRunStore(database);
const saved = store.save(report, "answer-quality-2026-11-08");
store.setBaseline("answer-quality", saved.runId);
const baseline = store.getBaseline("answer-quality");
// Close the database during application shutdown.
```

The store persists report and per-case score metadata only. It does not persist dataset inputs or model outputs. `InMemoryEvaluationRunStore` is available for tests and local development.
## Isolated subprocess worker

```ts
import { WorkerProcess } from "@spunkytech/agentops";

const worker = new WorkerProcess("node", ["worker-entrypoint.mjs"], {
  timeoutMs: 5_000,
  maxInputBytes: 256_000,
  maxOutputBytes: 256_000,
});
const result = await worker.execute("reports.summarize", { reportId: "r-123" });
```

The child reads one JSON line from stdin and writes one JSON line to stdout. It must echo protocol_version and request_id, and include result. A fresh process group is launched per call on POSIX; the group is terminated on completion, deadline, or output overflow so descendants cannot outlive the request. On Windows, the current adapter terminates the direct child only; use a container or external process supervisor if the worker can spawn descendants. This is process separation, not a sandbox; apply OS/container filesystem, network, privilege, CPU, memory, and PID controls for untrusted code.

## Docker-isolated worker

Build the example image from the repository root:

```bash
docker build -f examples/Dockerfile.worker -t agentops-example-worker:local .
```

```ts
import { DockerWorker } from "@spunkytech/agentops";

const worker = new DockerWorker("agentops-example-worker:local", {
  timeoutMs: 10_000,
  memoryLimitBytes: 512 * 1024 * 1024,
  cpuLimit: 1.5,
  pidsLimit: 32,
  maxConcurrentWorkers: 4,
});
const result = await worker.execute("identity.echo", { message: "hello" });
```

The image must be preloaded locally. Each call starts a fresh non-root container with no network or host mounts, a read-only root filesystem, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs, and a restricted temporary filesystem. Protocol byte limits and deadlines remain active. The Docker daemon and host kernel remain trusted; this profile is not escape-proof.

Each DockerWorker instance limits concurrent containers to four by default. Set `maxConcurrentWorkers` to tune the per-instance concurrency cap. The configured deadline covers both slot acquisition and worker execution; best-effort Docker cleanup may continue for up to five seconds after it expires. This is an in-process limit, not a cluster-wide quota.