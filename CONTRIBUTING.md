# Contributing

Contributions of code, tests, documentation, examples, and issue reports are welcome.

## Before you start
- Search existing issues and pull requests.
- For substantial changes, open an issue to align on the design.
- Keep changes focused and explain the problem they solve.
- Never include credentials, production data, or private customer information.

## Python setup
```bash
cd packages/python
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

## TypeScript setup
```bash
cd packages/typescript
npm install
npm test
```

## Pull requests
Include a problem statement, focused implementation, tests for success and failure paths, and documentation for public API changes. Explain compatibility and security impact. Avoid unrelated refactors.

For security-sensitive reports, follow SECURITY.md rather than opening a public issue.
