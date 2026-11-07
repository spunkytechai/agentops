# Security Model (0.4)

## Authorization
- Default decision is deny.
- Tool identifiers are exact strings; wildcard expansion is not supported.
- Global and principal-scoped explicit deny rules take precedence over every allow rule.
- Principal-scoped rules match only the exact principal ID and tool name.
- A denied operation is not invoked and emits no execution event.
- Policy construction snapshots caller-owned collections; mutating the input sets, arrays, or rule lists after construction cannot silently change authorization decisions.
- Policy evaluation is an application-level control, not a substitute for infrastructure isolation.

## Human approval workflow
- Approval requests are bound to an exact principal ID and tool identifier.
- Requests have a finite expiry and move through pending, approved, denied, expired, and consumed states.
- Only pending requests may be approved or denied.
- Approved requests can be consumed once; replay attempts fail.
- Expired, denied, pending, consumed, unknown, or mismatched requests do not produce grants.
- Python state transitions are protected by a process-local reentrant lock; TypeScript transitions are synchronous within one JavaScript isolate.
- The initial manager is in-memory. It is not durable, distributed, or safe for multi-worker coordination.
- The host application must authenticate approvers, authorize their decision scope, protect the approval endpoint, and bind approved action details to the actual invocation. A summary string alone is not a cryptographic binding to tool arguments.
- Approval never overrides tool policy. The application must evaluate policy independently before invoking a tool.

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
3. Authorize before invocation.
4. For consequential actions, create a human-readable approval request with the exact target and effect.
5. Authenticate and authorize the human approver in the host application.
6. Consume an approved grant once, immediately before executing the matching principal/tool action.
7. Bind approved action details to actual tool arguments; do not rely on display summaries alone.
8. Scope credentials to minimum required actions.
9. Validate arguments independently of model output.
10. Set finite timeouts and propagate cancellation through each integration.
11. Apply process, network, and resource isolation at infrastructure boundaries.
12. Redact sensitive data before exporting telemetry.

The threat model is preliminary and will evolve with the runtime and integration surface.
