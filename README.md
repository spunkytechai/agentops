# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It provides a consistent foundation for registering agent versions, governing tool access, human approval workflows, and recording execution behavior across Python and TypeScript applications.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## What exists today

- Versioned, process-local agent registry in Python and TypeScript.
- Deny-by-default tool authorization with global and principal-scoped rules.
- Explicit deny precedence across global and scoped permissions.
- Human approval state machine with pending, approved, denied, expired, and consumed states.
- Principal- and tool-bound, expiring, one-time approval grants.
- Synchronous and asynchronous tool execution in Python.
- Asynchronous TypeScript execution with configurable timeouts and abort signaling.
- Structured start, success, failure, and timeout events.
- In-memory recorders that exclude prompts, arguments, results, and credentials.
- Automated unit tests and CI across supported Python versions, plus Node.js.

## Why AgentOps?

AI agents combine probabilistic model output with tools that can read data, call APIs, and change external systems. Production systems need explicit boundaries, traceable execution, repeatable evaluation, and predictable failure handling.

## Repository layout

- `packages/python/` — Python SDK and runtime foundation
- `packages/typescript/` — TypeScript SDK foundation
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

## Human approval workflow

The approval manager is an explicit pre-execution workflow primitive. The host application creates a request, presents its summary to an authenticated human approver, records the decision, and consumes the grant immediately before the matching tool call.

```python
from agentops import ApprovalManager, ToolExecutor, ToolPolicy

approvals = ApprovalManager()
request = approvals.request(
    principal_id="authenticated-user-17",
    tool_name="payments.refund",
    summary="Refund order 1042 for INR 2,500",
    ttl_seconds=120,
)
# The host application must authenticate and authorize the approver.
approvals.approve(request.request_id, approver_id="finance-admin-2")

# Consume once, then execute the exact approved tool under normal policy.
approvals.consume(request.request_id, "authenticated-user-17", "payments.refund")
executor = ToolExecutor(ToolPolicy(frozenset({"payments.refund"})))
result = executor.execute("payments.refund", lambda: refund_order("1042"))
```

The application must ensure the operation arguments match the approved summary. Do not treat model-supplied identity as authenticated identity. Approval does not override a tool-policy deny.

## Security boundary

Policy and approval are application-level controls, **not a sandbox**. The approval manager and registry are process-local and non-persistent. The host application is responsible for authenticating approvers, authorizing who may approve which actions, protecting approval APIs, and persisting decisions where required. A one-time grant is bound to a principal and tool, but the host must bind the approved action details to the actual invocation. Timeouts request cancellation (Python task cancellation or TypeScript AbortSignal); a tool must cooperate with cancellation. A timeout does not terminate arbitrary native code, detached work, or external side effects already accepted by another service. Run untrusted code in a hardened worker/container and use least-privilege credentials. Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

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
- [ ] Policy composition and execution-integrated approval gates
- [ ] Persistent registry and distributed identity management
- [ ] OpenTelemetry exporters and evaluation engine
- [ ] Isolated worker adapters and deployment guides
- [ ] Independent security review before stable release

See [CONTRIBUTING.md](CONTRIBUTING.md) to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
