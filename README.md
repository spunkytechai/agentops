# AgentOps

**Build. Evaluate. Secure. Operate AI agents.**

AgentOps is an open-source, provider-agnostic toolkit for building reliable AI agent systems. It aims to give developers a consistent foundation for defining agents, governing tool access, recording executions, and evaluating behavior across model providers.

> **Project status:** Early development (0.x). APIs are experimental and may change.

## Why AgentOps?

AI agents combine probabilistic model output with tools that can read data, call APIs, and change external systems. Production systems need more than a prompt and a loop: they need explicit boundaries, traceable execution, repeatable evaluation, and predictable failure handling.

AgentOps is designed around those operational needs.

## Project goals

- **Provider-agnostic:** keep core interfaces independent of any one model vendor.
- **Secure by default:** make tool permissions explicit and deny unapproved actions.
- **Observable:** capture structured events for each agent run without requiring a hosted service.
- **Evaluatable:** support deterministic tests and repeatable scenario-based evaluations.
- **Self-hostable:** make local development and private deployments first-class.
- **Composable:** expose small APIs that can be adopted incrementally.

## Planned capabilities

| Area | Purpose |
| --- | --- |
| Agent contracts | Define agents, inputs, outputs, and execution context |
| Tool governance | Register tools and enforce allow/deny policies |
| Runtime | Execute bounded agent steps with timeouts and limits |
| Observability | Emit structured run, step, and tool-call events |
| Evaluation | Run scenario suites and score expected behavior |
| Adapters | Connect model providers through optional integrations |
| CLI | Inspect configuration, run checks, and execute evaluations |

## Repository layout

The repository is organized as a Python package, a TypeScript package, shared documentation, and examples:

- `packages/python/` — Python SDK and runtime foundation
- `packages/typescript/` — TypeScript SDK foundation
- `docs/` — architecture, security, and development guides
- `examples/` — minimal usage examples

## Quick start

The SDKs are being developed. Until the first installable release, clone the repository and follow the development setup in the package-specific README files.

## Development principles

1. Security boundaries must be enforced in code, not only documented in prompts.
2. Core functionality should work locally without a cloud account.
3. Telemetry must avoid collecting secrets by default.
4. Optional integrations must not become mandatory dependencies.
5. Public APIs need tests, examples, and migration notes.

## Roadmap

- [x] Public repository and project foundation
- [ ] Python core contracts and policy engine
- [ ] TypeScript core contracts and policy engine
- [ ] Runtime event model and in-memory recorder
- [ ] Cross-language conformance tests
- [ ] CLI, integrations, and deployment guides
- [ ] Security review and 0.1 release

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to participate and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Apache-2.0. See [LICENSE](LICENSE).
