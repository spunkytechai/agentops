# Contributing

Contributions of code, tests, documentation, examples, and issue reports are welcome. AgentOps is an early-stage project; public APIs may change before 1.0.

## Before you start

- Read the [README](README.md), [architecture](docs/ARCHITECTURE.md), and [security model](docs/SECURITY_MODEL.md).
- Search existing issues and pull requests before opening a new one.
- For substantial changes, open an issue first to align on scope and interfaces.
- Keep changes focused and explain the problem they solve.
- Never include credentials, production data, private prompts, or customer information.

## Prerequisites

- Python 3.10–3.13 for the Python SDK.
- Node.js 20 or newer and npm for the TypeScript SDK.
- Docker Engine only when running Docker worker integration tests.

## Python setup

Run these commands from the repository root (the `pyproject.toml` is at the root):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s packages/python/tests -v
```

## TypeScript setup

```bash
cd packages/typescript
npm install
npm test
```

The repository does not yet commit an npm lockfile. Until the lockfile and CI migration to `npm ci` are complete, dependency resolution is not guaranteed to be reproducible. Track progress in [issue #30](https://github.com/spunkytechai/agentops/issues/30).

## Docker integration tests

From the repository root, after installing both SDKs and ensuring Docker is running:

```bash
docker build -f examples/Dockerfile.worker -t agentops-example-worker:ci .
AGENTOPS_DOCKER_INTEGRATION=1 python -m unittest discover -s packages/python/tests -v
cd packages/typescript
AGENTOPS_DOCKER_INTEGRATION=1 npm test
```

## Pull requests

Include a problem statement, focused implementation, tests for success and failure paths, and documentation for public API changes. Explain compatibility and security impact. Avoid unrelated refactors.

Before requesting review:

- Run the relevant focused tests.
- Run the complete affected SDK test suite.
- Confirm formatting, type checks, and package builds where applicable.
- Update examples and docs when behavior or public APIs change.
- State exactly what you tested and what you did not test.

For security-sensitive reports, follow [SECURITY.md](SECURITY.md) rather than opening a public issue.
