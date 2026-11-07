# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It provides a consistent foundation for registering agent versions, governing tool access, human approval workflows, and recording execution behavior across Python and TypeScript applications.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## What exists today

- Versioned, process-local agent registry in Python and TypeScript.
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
- In-memory recorders that exclude prompts, arguments, results, and credentials.
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

## Security boundary

Policy and approval are application-level controls, **not a sandbox**. The agent registry remains process-local. SQLite approval storage provides durable state and atomic single-use transitions, but does not authenticate approvers or protect the database file. The host application is responsible for authenticating approvers, authorizing who may approve which actions, protecting approval APIs, and persisting decisions where required. Approval never overrides a policy deny. Timeouts request cancellation (Python task cancellation or TypeScript AbortSignal); a tool must cooperate with cancellation. A timeout does not terminate arbitrary native code, detached work, or external side effects already accepted by another service. Run untrusted code in a hardened worker/container and use least-privilege credentials. Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

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
- [ ] Persistent agent registry and server-database adapters
- [ ] Distributed identity and approval scopes
- [ ] OpenTelemetry exporters and evaluation engine
- [ ] Isolated worker adapters and deployment guides
- [ ] Independent security review before stable release

See [CONTRIBUTING.md](CONTRIBUTING.md) to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
