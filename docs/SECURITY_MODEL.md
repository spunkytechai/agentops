# Security Model (0.5)

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
- The in-memory approval manager is not durable or distributed. Multi-worker deployments require a transactional store with atomic compare-and-consume semantics.
- SHA-256 action fingerprints bind data equality; they do not authenticate a user, prove that the human understood the action, or prevent a malicious tool adapter from ignoring the approved payload.

## Human approval lifecycle
- Requests have a finite expiry and move through pending, approved, denied, expired, and consumed states.
- Only pending requests may be approved or denied.
- Approved requests can be consumed once; replay attempts fail.
- Expired, denied, pending, consumed, unknown, or mismatched requests do not produce grants.
- Python state transitions are protected by a process-local reentrant lock; TypeScript transitions are synchronous within one JavaScript isolate.

## Execution timeouts and cancellation
- Python async timeouts cancel the executing task and wait for cancellation handling.
- TypeScript timeouts reject the execution and abort the supplied `AbortSignal`.
- Tool integrations should propagate cancellation to HTTP clients, database drivers, and other cancellable dependencies.
- Cancellation is cooperative. It cannot forcibly stop arbitrary native code, detached work, or undo side effects already accepted by external systems.
- Do not treat a timeout as a sandbox or a guarantee that no external side effect occurred.

## Registry
The initial agent registry is process-local, in-memory, and non-persistent. It is not a distributed source of truth and does not provide cryptographic identity, deployment approval, or artifact integrity verification. Do not treat registration as proof that an agent definition or its tools are trusted.

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

The threat model is preliminary and will evolve with the runtime and integration surface.
