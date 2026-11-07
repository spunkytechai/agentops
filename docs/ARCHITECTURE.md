# Architecture

## Initial foundation
The Python and TypeScript SDKs share four conceptual primitives:
1. **Policy:** exact tool identifiers, explicit allow-list, explicit deny-list, deny precedence.
2. **Execution boundary:** authorization happens before an operation is invoked.
3. **Events:** lifecycle metadata for start, success, and failure.
4. **Recorder:** pluggable event sink with an in-memory local implementation.

Core packages are dependency-light and provider-neutral.

## Trust boundaries
Model output is untrusted. A model proposing a tool call does not authorize it. The host application maps tool names to concrete operations and routes each operation through the policy-enforcing executor.

The executor is an application-level authorization boundary, not a sandbox. It does not isolate processes, constrain network access, or impose CPU/memory limits. Untrusted code must run in a hardened worker or container.

## Data minimization
The default recorder stores tool name, run ID, event type, timestamp, duration, and error class. It excludes prompts, arguments, results, headers, tokens, and exception messages.

## Planned evolution
- versioned agent and tool contracts;
- async and streaming runtime;
- scoped identities and policy composition;
- OpenTelemetry-compatible exporters;
- evaluation datasets and deterministic replay;
- isolated worker adapters and resource budgets.

Cross-language behavior should be specified by shared conformance fixtures before expanding the public API.
