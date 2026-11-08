# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It provides a consistent foundation for registering agent versions, governing tool access, human approval workflows, and recording execution behavior across Python and TypeScript applications.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## What exists today

- Versioned agent registry in Python and TypeScript, with in-memory and durable SQLite stores.
- Atomic duplicate-version protection across independent SQLite connections.
- Shared Python/TypeScript agent registry conformance fixture.
- Deny-by-default tool authorization with global and principal-scoped rules.
- Explicit deny precedence across global and scoped permissions.
- Human approval state machine with pending, approved, denied, expired, and consumed states.
- Pluggable approval-store contract with in-memory and SQLite implementations in both SDKs.
- Atomic SQLite compare-and-consume; a grant cannot be consumed twice by competing workers.
- Principal-, tool-, and canonical-action-bound, expiring, one-time approval grants.
- Execution-integrated approval gates in both SDKs.
- Synchronous and asynchronous tool execution in Python.
- Asynchronous TypeScript execution with configurable timeouts and abort signaling.
- Structured start, success, failure, and timeout events.
- W3C-compatible trace, span, and parent-span identifiers propagated through execution lifecycle events in both SDKs.
- In-memory recorders that exclude prompts, arguments, results, and credentials.
- OTLP/HTTP JSON trace export in both SDKs, with bounded queues, batching, retries, and allowlisted span attributes.
- Deterministic evaluation suites with weighted cases, exact-match and numeric-tolerance metrics, per-case reports, and baseline regression detection.
- Shared Python/TypeScript evaluation conformance fixture.
- Shared cross-language policy and action-fingerprint fixtures.
- Automated unit tests and CI across supported Python versions, plus Node.js.

## Why AgentOps?

AI agents combine probabilistic model output with tools that can read data, call APIs, and change external systems. Production systems need explicit boundaries, traceable execution, repeatable evaluation, and predictable failure handling.

## Repository layout

- `packages/python/` — Python SDK and runtime foundation
- `packages/typescript/` — TypeScript SDK foundation
- `conformance/fixtures/` — language-neutral behavioral fixtures
- `docs/` — architecture and security model
- `examples/` — minimal usage examples

## Quick start

### Python

```bash
python -m pip install -e .
python -m unittest discover -s packages/python/tests -v
```

```python
import asyncio
from agentops import ToolExecutor, ToolPolicy

async def main():
    executor = ToolExecutor(ToolPolicy(frozenset({"weather.lookup"})))
    result = await executor.execute_async(
        "weather.lookup",
        lambda: fetch_weather(),
        timeout_seconds=5,
    )
    print(result)

asyncio.run(main())
```

### TypeScript

```bash
cd packages/typescript
npm install
npm test
```

```ts
const result = await executor.execute(
  "weather.lookup",
  async (signal) => fetchWeather({ signal }),
  "weather-run-1",
  { timeoutMs: 5000 },
);
```

## Action-bound human approval

For consequential actions, bind the approval to the exact action payload and use the execution-integrated gate. The executor checks policy first, consumes the matching approval once, and passes the canonical action snapshot to the operation.

```python
from agentops import ApprovalManager, PolicyRule, ToolExecutor, ToolPolicy

action = {"order_id": "1042", "amount": 2500, "currency": "INR"}
approvals = ApprovalManager()
request = approvals.request(
    principal_id="authenticated-user-17",
    tool_name="payments.refund",
    summary="Refund order 1042 for INR 2,500",
    action=action,
    ttl_seconds=120,
)
# The host application must authenticate and authorize the approver.
approvals.approve(request.request_id, approver_id="finance-admin-2")

executor = ToolExecutor(ToolPolicy(rules=(
    PolicyRule("authenticated-user-17", "payments.refund", "allow"),
)))
result = executor.execute_approved(
    "payments.refund",
    lambda approved_action: refund_order(**approved_action),
    principal_id="authenticated-user-17",
    approval_manager=approvals,
    approval_request_id=request.request_id,
    action=action,
)
```

TypeScript exposes the equivalent `executeApproved` method. Its operation callback receives the approved action and an `AbortSignal`.

Action payloads use deterministic JSON canonicalization and SHA-256. To guarantee identical fingerprints across Python and TypeScript, payloads support JSON objects, arrays, strings, booleans, null, and safe integers. Floating-point numbers are rejected; represent monetary values as integer minor units or decimal strings.

The executor passes a canonical snapshot of the payload whose fingerprint was approved. Tool adapters must use that supplied object as the actual invocation input; do not reconstruct or substitute hidden arguments. Principal IDs must come from trusted host authentication, never model output.

## Durable approval storage

Python uses the standard-library SQLite driver:

```python
from agentops import ApprovalManager, SqliteApprovalStore

approvals = ApprovalManager(store=SqliteApprovalStore("agentops.sqlite3"))
```

TypeScript accepts a synchronous SQLite database handle compatible with `better-sqlite3`:

```ts
import Database from "better-sqlite3";
import { ApprovalManager, SqliteApprovalStore } from "@spunkytech/agentops";

const database = new Database("agentops.sqlite3");
const approvals = new ApprovalManager({ store: new SqliteApprovalStore(database) });
```

The SQLite adapter consumes a grant through one conditional SQL update that checks the request, principal, tool, action fingerprint, approved state, approver, and expiry. Competing consumers cannot both succeed. Workers must share the same database file on storage with reliable SQLite locking; use a transactional server database for multi-host deployments. The TypeScript host supplies and owns the synchronous SQLite driver and connection lifecycle.

## Durable agent registry

The default registry is in-memory. For persistent registrations, Python uses the standard-library SQLite driver:

```python
from agentops import AgentDefinition, AgentRegistry, SqliteAgentRegistryStore

store = SqliteAgentRegistryStore("agentops.sqlite3")
registry = AgentRegistry(store=store)
registry.register(AgentDefinition(
    "support.assistant", "1.0.0", "Customer support agent",
    ("knowledge.search", "ticket.create"),
))
# Close the store during application shutdown.
store.close()
```

TypeScript accepts a synchronous SQLite database handle:

```ts
import Database from "better-sqlite3";
import { AgentDefinition, AgentRegistry, SqliteAgentRegistryStore } from "@spunkytech/agentops";

const database = new Database("agentops.sqlite3");
const registry = new AgentRegistry({ store: new SqliteAgentRegistryStore(database) });
registry.register(new AgentDefinition({
  agentId: "support.assistant", version: "1.0.0",
  description: "Customer support agent",
  tools: ["knowledge.search", "ticket.create"],
}));
// Close the database during application shutdown.
database.close();
```

Both SDKs share the `agentops_agents` SQLite schema. The composite primary key (`agent_id`, `version`) rejects duplicate registration across connections; existing versions are never overwritten. Tool identifiers are stored as a JSON array. SQLite is suitable for a single host or workers sharing a correctly locked database file. Use a transactional server-database implementation for multi-host deployments.

## Trace correlation

Both SDKs expose an immutable `TraceContext` with W3C Trace Context-compatible 32-character trace IDs and 16-character span IDs. A tool execution accepts an optional context; when omitted, the executor creates one. All lifecycle events for that execution share the same trace and span identifiers. Use `TraceContext.create(parent)` to create a child span context that retains the trace ID and records the parent span ID.

Python:

```python
from agentops import TraceContext

parent = TraceContext.create()
child = TraceContext.create(parent)
executor.execute("reports.read", operation, trace_context=child)
```

TypeScript:

```ts
import { TraceContext } from "@spunkytech/agentops";

const parent = TraceContext.create();
const child = TraceContext.create(parent);
await executor.execute("reports.read", operation, "report-run-1", { traceContext: child });
```

Trace context can be exported as completed OTLP spans using `OtlpHttpSpanExporter` in either SDK. The exporter implements the OTLP/HTTP JSON trace request shape and accepts an injected transport (synchronous in Python, asynchronous in TypeScript); no OpenTelemetry SDK or networking dependency is required. Call `flush()` from a worker or shutdown hook (await it in TypeScript). The exporter only emits allowlisted operational attributes; it never serializes prompts, arguments, results, exception messages, or credentials. This is an OTLP exporter, not a complete OpenTelemetry SDK: automatic instrumentation, metrics, logs, sampling, and `traceparent` propagation remain out of scope.

## Agent evaluation and regression detection

The evaluation engine runs fixed JSON-compatible datasets against a supplied operation, scores each case with a pluggable metric, and produces weighted aggregate score and pass rate. Built-in metrics include exact JSON-value matching and numeric tolerance. Operation failures are recorded by exception class only; exception messages and model/tool payloads are not copied into reports. Compare baseline and candidate reports to detect aggregate score drops and identify regressed case IDs. The SDK runs cases sequentially; it does not call an LLM, create datasets, or guarantee deterministic model behavior. Store datasets and reports under the host application's access controls.

```python
from agentops import EvaluationCase, EvaluationSuite, ExactMatchMetric, compare_evaluations

suite = EvaluationSuite("smoke", [
    EvaluationCase("greeting", {"prompt": "hello"}, "Hello!", weight=2),
], metric=ExactMatchMetric())
report = suite.run(lambda item: "Hello!")
print(report.weighted_score, report.pass_rate)
# Compare a later report with the stored baseline.
# regression = compare_evaluations(baseline, report)
```

Evaluation reports can be persisted using `EvaluationRunStore` or `SqliteEvaluationRunStore`. Run IDs are unique, and each suite has one replaceable baseline pointer. Baseline updates are accepted only for an existing run from that exact suite. Python and TypeScript share the same SQLite schema and report JSON field names.

## Security boundary

Policy and approval are application-level controls, **not a sandbox**. The default agent registry is process-local; its optional SQLite store persists immutable definitions across restarts but does not verify agent artifacts or publisher identity. SQLite approval storage provides durable state and atomic single-use transitions, but does not authenticate approvers or protect the database file. The host application is responsible for authenticating approvers, authorizing who may approve which actions, protecting approval APIs, and persisting decisions where required. Approval never overrides a policy deny. Timeouts request cancellation (Python task cancellation or TypeScript AbortSignal); a tool must cooperate with cancellation. A timeout does not terminate arbitrary native code, detached work, or external side effects already accepted by another service. Run untrusted code in a hardened worker/container and use least-privilege credentials. Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Roadmap

- [x] Public repository and project foundation
- [x] Python and TypeScript policy/runtime foundations
- [x] Metadata-only execution event recording
- [x] Versioned in-memory agent registry
- [x] Principal-scoped policy rules
- [x] Async Python execution and bounded TypeScript execution
- [x] Timeout error recording and cancellation signaling
- [x] Initial unit tests and CI workflow
- [x] In-memory human approval state machine
- [x] Shared cross-language policy conformance fixture and immutable policy snapshots
- [x] Canonical action fingerprints and execution-integrated approval gates
- [x] Pluggable approval storage and durable SQLite adapters
- [x] Persistent agent registry with shared Python/TypeScript SQLite schema
- [ ] Transactional server-database adapters for multi-host deployments
- [ ] Distributed identity and approval scopes
- [x] Initial OTLP/HTTP JSON trace exporter for Python and TypeScript
- [ ] OpenTelemetry SDK integration, sampling, and automatic instrumentation
- [x] Deterministic evaluation engine and baseline regression comparison
- [x] Persistent evaluation run history and suite-specific baselines
- [ ] Isolated worker adapters and deployment guides
- [ ] Independent security review before stable release

See [CONTRIBUTING.md](CONTRIBUTING.md) to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
