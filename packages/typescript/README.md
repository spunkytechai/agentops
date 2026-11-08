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

When omitted, the executor creates trace and span identifiers. Export completed tool spans using an injected synchronous HTTP transport:


```ts
import { OtlpHttpSpanExporter, ToolExecutor } from "@spunkytech/agentops";

const exporter = new OtlpHttpSpanExporter("http://localhost:4318", (url, headers, body) => {
  // Send an HTTP POST with these headers and body using your preferred HTTP client.
  // Throw on non-2xx responses so the exporter can retry the batch.
});
const executor = new ToolExecutor(policy, exporter);
// Call exporter.flush() from a worker or controlled shutdown hook.
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
