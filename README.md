# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It provides a consistent foundation for governing tool access and recording execution behavior across Python and TypeScript applications.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## What exists today

- Python and TypeScript tool authorization policies.
- Deny-by-default access control with explicit-deny precedence.
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

### TypeScript

```bash
cd packages/typescript
npm install
npm test
```

## Security boundary

The current executor is an application-level authorization boundary, **not a sandbox**. It does not isolate processes, restrict network access, or impose resource limits. Run untrusted code in a hardened worker/container and use least-privilege credentials. Read [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).

## Roadmap

- [x] Public repository and project foundation
- [x] Python and TypeScript policy/runtime foundations
- [x] Metadata-only execution event recording
- [x] Initial unit tests and CI workflow
- [ ] Shared cross-language conformance fixtures
- [ ] Async runtime, scoped identities, and policy composition
- [ ] OpenTelemetry exporters and evaluation engine
- [ ] Isolated worker adapters and deployment guides
- [ ] Independent security review before stable release

See [CONTRIBUTING.md](CONTRIBUTING.md) to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
