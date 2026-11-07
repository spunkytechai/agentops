# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It provides a consistent foundation for registering agent versions, governing tool access, and recording execution behavior across Python and TypeScript applications.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## What exists today

- Versioned, process-local agent registry in Python and TypeScript.
- Deny-by-default tool authorization with global and principal-scoped rules.
- Explicit deny precedence across global and principal-scoped permissions.
- Execution wrappers that authorize before invoking tools.
- Structured start, success, and failure events.
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
from agentops import AgentDefinition, AgentRegistry, PolicyRule, ToolPolicy

registry = AgentRegistry()
registry.register(AgentDefinition(
    agent_id="support.assistant",
    version="1.0.0",
    tools=("knowledge.search", "ticket.create"),
))

policy = ToolPolicy(rules=(
    PolicyRule("support-agent", "knowledge.search", "allow"),
))
assert policy.evaluate("knowledge.search", principal_id="support-agent").allowed
```

### TypeScript

```bash
cd packages/typescript
npm install
npm test
```

## Security boundary

Global and principal-scoped policy rules are application-level authorization controls, **not a sandbox**. The current registry is process-local and does not persist or coordinate across replicas. The executor does not isolate processes, restrict network access, or impose resource limits. Run untrusted code in a hardened worker/container and use least-privilege credentials. Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Roadmap

- [x] Public repository and project foundation
- [x] Python and TypeScript policy/runtime foundations
- [x] Metadata-only execution event recording
- [x] Versioned in-memory agent registry
- [x] Principal-scoped policy rules
- [x] Initial unit tests and CI workflow
- [ ] Shared cross-language conformance fixtures
- [ ] Async runtime, policy composition, and approval workflows
- [ ] Persistent registry and distributed identity management
- [ ] OpenTelemetry exporters and evaluation engine
- [ ] Isolated worker adapters and deployment guides
- [ ] Independent security review before stable release

See [CONTRIBUTING.md](CONTRIBUTING.md) to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
