# Security Model (0.6)

## Authorization
- Default decision is deny.
- Tool identifiers are exact strings; wildcard expansion is not supported.
- Global and principal-scoped explicit deny rules take precedence over every allow rule.
- Principal-scoped rules match only the exact principal ID and tool name.
- The executor evaluates policy before consuming an approval; a policy deny leaves the approval pending/approved and does not invoke the operation.
- Policy construction snapshots caller-owned collections; mutating the input sets, arrays, or rule lists after construction cannot silently change authorization decisions.
- Policy evaluation is an application-level control, not a substitute for infrastructure isolation.

## Action-bound human approval
- Approval requests may include a canonical action fingerprint in addition to the principal and tool identifiers.
- The fingerprint is SHA-256 over deterministic UTF-8 JSON with recursively sorted object keys.
- Cross-language payloads support JSON objects, arrays, strings, booleans, null, and safe integers. Floating-point values and non-JSON values are rejected; use integer minor units or decimal strings for money.
- Execution-integrated gates compare the supplied action fingerprint before invoking the operation and consume the approval exactly once.
- The operation callback receives a canonical snapshot of the approved action; integrations must use that exact object as the actual tool input.
- A changed amount, target, resource ID, or other action field produces a different fingerprint and is rejected before invocation.
- Principal IDs must be derived from trusted host authentication, not model-generated content.
- The executor does not authenticate approvers. The host application must authenticate the approver, authorize their scope, and protect the decision endpoint.
- SHA-256 action fingerprints bind data equality; they do not authenticate a user, prove that the human understood the action, or prevent a malicious tool adapter from ignoring the approved payload.

## Durable approval storage
- Both SDKs expose an `ApprovalStore` contract, an `InMemoryApprovalStore` default, and a `SqliteApprovalStore` adapter.
- Python uses the standard-library `sqlite3` module. TypeScript accepts a synchronous SQLite database handle; the integration tests use `better-sqlite3`.
- Consumption is a single conditional SQL `UPDATE` matching request ID, principal, tool, action fingerprint, approved status, non-null approver, and expiry. Only one competing update can change approved to consumed.
- SQLite persistence survives manager/process restarts when the same database file is reopened. Both SDKs use the shared `expires_at_ms` column in Unix epoch milliseconds; Python converts its seconds-based public clock at the storage boundary.
- Workers must share the same database file on storage with reliable SQLite locking. For multi-host deployments, use a transactional server database.
- Keep the database private, access-controlled, and backed up. The SDK does not encrypt summaries or fingerprints.
- Custom `ApprovalStore` implementations must enforce atomic compare-and-consume semantics across workers; read-then-write is unsafe.
- The TypeScript SQLite adapter is synchronous; offload it from latency-sensitive event loops or supply an async transactional adapter.

## Human approval lifecycle
- Requests have a finite expiry and move through pending, approved, denied, expired, and consumed states.
- Only pending requests may be approved or denied.
- Approved requests can be consumed once; replay attempts fail.
- Expired, denied, pending, consumed, unknown, or mismatched requests do not produce grants.
- The in-memory store uses a process-local lock in Python and synchronous state transitions in TypeScript. SQLite uses conditional SQL updates for state transitions and consumption.

## Execution timeouts and cancellation
- Python async timeouts cancel the executing task and wait for cancellation handling.
- TypeScript timeouts reject the execution and abort the supplied `AbortSignal`.
- Tool integrations should propagate cancellation to HTTP clients, database drivers, and other cancellable dependencies.
- Cancellation is cooperative. It cannot forcibly stop arbitrary native code, detached work, or undo side effects already accepted by external systems.
- Do not treat a timeout as a sandbox or a guarantee that no external side effect occurred.

## Agent registry
- Both SDKs expose an `AgentRegistryStore` contract with in-memory and SQLite implementations.
- The shared `agentops_agents` table stores `agent_id`, `version`, `description`, and `tools_json`; both SDKs use JSON arrays for tool identifiers.
- A composite primary key on `(agent_id, version)` makes duplicate registration atomic across independent SQLite connections. Existing versions are immutable; registration never updates or overwrites an existing record.
- The SQLite store persists definitions across process restarts when the same database is reopened. The application owns connection lifecycle and database access controls.
- SQLite is suitable for a single host or workers sharing a database file on storage with reliable locking. Use a transactional server database for multi-host deployments and implement the same atomic create contract.
- The default in-memory store remains process-local and non-durable.
- The registry does not authenticate publishers, verify agent artifacts, approve deployment, or prove that declared tools are safe. Do not treat registration as proof that an agent definition or its tools are trusted.

## Trace metadata and telemetry
- Trace IDs, span IDs, and parent-span IDs are correlation metadata, not authentication credentials or authorization claims.
- Both SDKs validate non-zero lowercase hexadecimal identifiers using W3C Trace Context identifier widths.
- Trace context is caller-controlled when explicitly supplied. Do not treat it as proof of caller identity or trust it across an untrusted boundary without validation and context replacement at the host boundary.
- The OTLP/HTTP JSON exporter serializes only an explicit allowlist: run ID, tool name, status, duration, and error class. Prompts, tool arguments, results, exception messages, arbitrary event metadata, and credentials are excluded.
- The exporter uses an injected transport and adds no mandatory networking or OpenTelemetry SDK dependency. The host transport owns TLS, authentication, timeout, and response validation.
- Pending and completed spans are bounded; overflow increments a dropped-span counter. Failed batches are retained and retried up to the configured attempt limit; if all attempts fail, `flush()` raises and leaves the batch queued.
- Python `flush()` is synchronous; TypeScript `flush()` is asynchronous. Run flushing in a worker or controlled shutdown hook, not on a latency-sensitive execution path.
- This release does not implement automatic instrumentation, metrics, logs, sampling, `traceparent` header parsing, or a complete OpenTelemetry SDK.

## Subprocess worker boundary

The Python and TypeScript WorkerProcess adapters launch a fresh child process per call and exchange a single versioned JSONL request/response. They reject requests exceeding the configured serialized input byte limit before process creation, stream and cap stdout bytes, enforce a wall-clock deadline, validate the protocol version and request correlation ID, and kill/reap a child that times out or exceeds the output budget. Stderr is discarded by default. These controls bound protocol payloads and execution time; they do not impose CPU, memory, process-count, filesystem, or network limits on the child.

**A subprocess is not a secure sandbox.** A child normally inherits the host user's OS permissions and may inherit environment variables, open handles, and network access. For untrusted code, run the worker inside an OS/container isolation profile: non-root identity, dropped capabilities, read-only/minimal filesystem, isolated temporary directory, no host socket mounts, explicit egress-deny network policy, CPU/memory/PID limits, seccomp/AppArmor/SELinux or equivalent controls, and narrowly scoped credentials. Apply limits at the infrastructure boundary and test the actual deployment profile. Do not treat this SDK adapter as a substitute for those controls.

The protocol is one request per process, not a pool or multi-tenant scheduler. JSON serialization excludes unsupported values; the host must validate schemas and authorize tool names before dispatch. Worker errors intentionally omit stderr and arbitrary exception text. A killed process cannot roll back side effects already committed to external systems.

## Docker container worker profile

`DockerWorker` wraps the bounded JSONL `WorkerProcess` adapter with a fresh, uniquely named Docker container for every invocation. The adapter uses a preloaded image (`--pull=never`), does not mount host paths or forward host environment variables, and applies a fixed profile: `--network=none`, `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, UID/GID 65532, memory and equal memory-swap limits, CPU quota, PID limit, and a size-limited `/tmp` tmpfs with `noexec,nosuid,nodev`. Only resource budgets are configurable; callers cannot disable the security flags through the public adapter. The existing request/response byte limits and execution deadline continue to apply.

Containers are named before launch. Docker `--rm` removes normal exits, and the host issues a bounded `docker rm --force` cleanup after success, protocol failure, timeout, or output overflow. Cleanup is best-effort when the daemon is unavailable. A killed client or unavailable daemon can leave an orphan container; production deployments should monitor container inventory and enforce daemon-level quotas. The adapter starts one container per call and does not provide a persistent pool or distributed scheduler.

**Docker is not an escape-proof sandbox.** Containers share the host kernel, and access to a privileged Docker daemon is effectively host-level authority. Keep the daemon and kernel patched, protect the Docker socket, prefer rootless Docker or user-namespace remapping, avoid privileged daemon configurations, and apply host-level quotas. For hostile multi-tenant code, consider gVisor, Kata Containers, or microVMs, and validate the actual deployed profile with a security review. Do not mount the Docker socket inside the worker. No host credentials are injected by this adapter; use narrowly scoped, explicit secret delivery only if the workload requires it.

## Limitations
The initial SDK is not a process sandbox, secret manager, network firewall, prompt-injection detector, model-output validator, or distributed audit log. An allow-list does not replace least-privilege credentials or infrastructure isolation.

## Integration checklist
1. Give each tool a stable namespaced identifier (for example, `calendar.read`).
2. Bind authenticated principal IDs in trusted host code; never accept a model-generated principal as authority.
3. Authorize every invocation through the policy-enforcing executor.
4. For consequential actions, create an approval request containing the exact action payload and a concise human-readable summary.
5. Authenticate and authorize the human approver in the host application.
6. Call the execution-integrated approval gate with the same action payload used to create the request.
7. Use the action object passed into the operation callback as the actual tool input; never silently reconstruct it.
8. Use integer minor units or decimal strings for monetary values to preserve cross-language fingerprint parity.
9. Scope credentials to minimum required actions and validate arguments independently of model output.
10. Set finite timeouts and propagate cancellation through each integration.
11. Apply process, network, and resource isolation at infrastructure boundaries.
12. Redact sensitive data before exporting telemetry.
13. Treat trace context as correlation only; derive identity and authorization from trusted host authentication.

The threat model is preliminary and will evolve with the runtime and integration surface.

## Evaluation data handling

Evaluation cases and reports are application data, not a secure dataset repository. Inputs are passed to the operation callback and may contain sensitive information; the host owns dataset access control, retention, and storage. The engine records operation exception class names only, never exception messages, prompts, or actual outputs in the report. Custom metrics execute in-process and must be treated as trusted code. Exact-match inputs are restricted to finite JSON-compatible values; integer values must be safe across JavaScript and Python.

## Evaluation history and baselines

The evaluation run store persists only aggregate reports and per-case score metadata. It does not persist dataset inputs, expected values, model outputs, prompts, or exception messages. Run IDs are unique and baseline pointers are suite-scoped; callers cannot set a baseline to a run belonging to a different suite. SQLite files still require host-level filesystem permissions, backup, retention, and encryption controls. The store is not a tamper-evident audit log.
