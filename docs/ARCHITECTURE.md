# Architecture

## Core primitives
The Python and TypeScript SDKs share five conceptual primitives:

1. **Agent definition:** immutable agent ID, version, description, and declared tool identifiers.
2. **Agent registry:** process-local lookup keyed by exact agent ID and version; duplicate versions are rejected.
3. **Policy:** exact tool identifiers, global allow/deny sets, and principal-scoped allow/deny rules.
4. **Execution boundary:** authorization happens before an operation is invoked; asynchronous calls can be bounded by a timeout.
5. **Events and recorder:** lifecycle metadata for start, success, and failure, sent to a pluggable event sink.

Core packages are dependency-light and provider-neutral.

## Registry semantics
The initial registry is in-memory and local to one process. It supports exact version retrieval and deterministic listing. It does not resolve semantic-version ranges, persist data, coordinate replicas, or imply that an agent definition is executable. A future persistence layer must preserve immutable version identity and explicit conflict handling.

## Policy evaluation order
1. Validate the requested tool identifier and optional principal identifier.
2. Apply global deny rules and matching principal-scoped deny rules.
3. Apply a global allow rule.
4. Apply a matching principal-scoped allow rule.
5. Deny if no allow rule matched.

An explicit deny always wins, including when a global allow also matches. Both SDKs snapshot caller-owned policy collections at construction so later mutations cannot alter an already-created policy. Shared JSON conformance fixtures are executed by both language test suites. Scoped rules match only the exact principal and tool identifiers. Wildcards and implicit role inheritance are not supported.

## Runtime and cancellation
Python `execute_async` uses task cancellation when its timeout expires. TypeScript `execute` rejects on timeout and aborts the supplied `AbortSignal`. Integrations must propagate and honor cancellation. JavaScript promises and Python coroutines cannot forcibly terminate arbitrary native code or reverse side effects already committed by an external system. Timeouts are not process isolation.

## Trust boundaries
Model output is untrusted. A model proposing a tool call does not authorize it. The host application maps tool names to concrete operations and routes each operation through the policy-enforcing executor.

The executor is an application-level authorization boundary, not a sandbox. It does not isolate processes, constrain network access, or impose CPU/memory limits. Untrusted code must run in a hardened worker or container.

## Data minimization
The default recorder stores tool name, run ID, event type, timestamp, duration, and error class. It excludes prompts, arguments, results, headers, tokens, and exception messages.

## Planned evolution
- shared cross-language conformance fixtures;
- persistent registry and scoped identities;
- policy composition and human approval workflows;
- OpenTelemetry-compatible exporters;
- evaluation datasets and deterministic replay;
- isolated worker adapters and resource budgets.
