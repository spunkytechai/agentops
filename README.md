# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It provides a consistent foundation for registering agent versions, governing tool access, and recording execution behavior across Python and TypeScript applications.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## What exists today

- Versioned, process-local agent registry in Python and TypeScript.
- Deny-by-default tool authorization with global and principal-scoped rules.
- Explicit deny precedence across global and scoped permissions.
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

## Security boundary

Global and principal-scoped policy rules are application-level authorization controls, **not a sandbox**. The registry is process-local and non-persistent. Timeouts request cancellation (Python task cancellation or TypeScript AbortSignal); a tool must cooperate with cancellation. A timeout does not terminate arbitrary native code, detached work, or external side effects already accepted by another service. Run untrusted code in a hardened worker/container and use least-privilege credentials. Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Roadmap

- [x] Public repository and project foundation
- [x] Python and TypeScript policy/runtime foundations
- [x] Metadata-only execution event recording
- [x] Versioned in-memory agent registry
- [x] Principal-scoped policy rules
- [x] Async Python execution and bounded TypeScript execution
- [x] Timeout error recording and cancellation signaling
- [x] Initial unit tests and CI workflow
- [ ] Shared cross-language conformance fixtures
- [ ] Policy composition and approval workflows
- [ ] Persistent registry and distributed identity management
- [ ] OpenTelemetry exporters and evaluation engine
- [ ] Isolated worker adapters and deployment guides
- [ ] Independent security review before stable release

See [CONTRIBUTING.md](CONTRIBUTING.md) to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
